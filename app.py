from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import requests
import time
import psycopg2
import os
import threading
from datetime import date, timedelta, datetime, timezone


app = Flask(__name__, static_folder="static")
CORS(app)

LEETCODE_GRAPHQL = "https://leetcode.com/graphql"

# Simple cache (in-memory)
CACHE = {}
TTL_SECONDS = 120  # 10 min


def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    exp, data = item
    if time.time() > exp:
        CACHE.pop(key, None)
        return None
    return data


def cache_set(key, data, ttl=TTL_SECONDS):
    CACHE[key] = (time.time() + ttl, data)


# GraphQL query
USER_PROFILE_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile {
      ranking
      reputation
    }
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
      }
    }
  }
}
"""


# improved fetch with retries and better headers


def fetch_leetcode(username: str, retries=2, timeout=30):
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com",
        "User-Agent": "Mozilla/5.0 (compatible; LeetStats/1.0; +https://your-site.example)",
        "Accept": "application/json",
    }

    payload = {"query": USER_PROFILE_QUERY,
               "variables": {"username": username}}

    for attempt in range(retries + 1):
        try:
            r = requests.post(LEETCODE_GRAPHQL, json=payload,
                              headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as http_err:
            status = getattr(http_err.response, "status_code", None)
            if status in (429, 499) or (status and 500 <= status < 600):
                if attempt < retries:
                    time.sleep(1 + attempt * 1)
                    continue
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < retries:
                time.sleep(1 + attempt * 0.5)
                continue
            raise
    raise RuntimeError("Failed to fetch leetcode profile after retries")


def transform_response(data):
    matched = data.get("data", {}).get("matchedUser")
    if not matched:
        return {"ok": False}

    profile = matched.get("profile") or {}
    stats = matched.get("submitStatsGlobal") or {}

    ac_list = stats.get("acSubmissionNum", [])
    solved = {i["difficulty"]: i["count"] for i in ac_list}

    easy = solved.get("Easy", 0)
    medium = solved.get("Medium", 0)
    hard = solved.get("Hard", 0)

    # ✅ ALWAYS compute total yourself
    total = easy + medium + hard

    return {
        "ok": True,
        "username": matched["username"],
        "ranking": profile.get("ranking"),
        "reputation": profile.get("reputation"),
        "solved": {
            "Easy": easy,
            "Medium": medium,
            "Hard": hard,
            "Total": total,
        }
    }




# ---------- DATABASE SETUP (PostgreSQL) ---------- #


def get_db_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in environment")

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    try:
        return psycopg2.connect(url, sslmode="require")
    except Exception:
        return psycopg2.connect(url)


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leetcode_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            ranking INTEGER,
            reputation INTEGER,
            easy INTEGER DEFAULT 0,
            medium INTEGER DEFAULT 0,
            hard INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            total_7d_ago INTEGER,
            total_30d_ago INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_total INTEGER,
            last_active_date DATE,
            current_streak INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()



def ensure_db():
    try:
        init_db()
        app.logger.info("Database initialized successfully.")
    except Exception as e:
        app.logger.error("Failed to initialize DB: %s", e)


ensure_db()


def store_user_stats(username, stats):
    conn = get_db_connection()
    cursor = conn.cursor()

    solved = stats.get("solved", {})

    # ✅ ALWAYS compute total from difficulties
    easy = solved.get("Easy", 0)
    medium = solved.get("Medium", 0)
    hard = solved.get("Hard", 0)
    new_total = easy + medium + hard

    cursor.execute("""
        SELECT last_total, last_active_date, current_streak,
               total_7d_ago, total_30d_ago, last_updated, total
        FROM leetcode_users
        WHERE username = %s
    """, (username,))
    row = cursor.fetchone()

    last_total = row[0] if row else None
    last_active_date = row[1] if row else None
    current_streak = row[2] if row else 0
    total_7d_ago = row[3] if row else None
    total_30d_ago = row[4] if row else None
    last_updated = row[5] if row else None
    old_total = row[6] if row else None

    today = date.today()

    # ✅ ACTIVITY + STREAK (FIXED & SAFE)
    if last_total is not None and new_total > last_total:
        if last_active_date == today - timedelta(days=1):
            current_streak += 1
        else:
            current_streak = 1
        last_active_date = today
    elif last_active_date and (today - last_active_date).days > 1:
        current_streak = 0

    now = datetime.now(timezone.utc)

    # ✅ TREND SNAPSHOT LOGIC (SAFE)
    if old_total is not None and last_updated:
        days_gap = (now - last_updated).days
        if total_7d_ago is None or days_gap >= 7:
            total_7d_ago = old_total
        if total_30d_ago is None or days_gap >= 30:
            total_30d_ago = old_total

    cursor.execute("""
        INSERT INTO leetcode_users
        (username, ranking, reputation, easy, medium, hard, total,
         total_7d_ago, total_30d_ago,
         last_updated, last_total, last_active_date, current_streak)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,
                CURRENT_TIMESTAMP,%s,%s,%s)
        ON CONFLICT (username)
        DO UPDATE SET
            ranking = EXCLUDED.ranking,
            reputation = EXCLUDED.reputation,
            easy = EXCLUDED.easy,
            medium = EXCLUDED.medium,
            hard = EXCLUDED.hard,
            total = EXCLUDED.total,
            total_7d_ago = EXCLUDED.total_7d_ago,
            total_30d_ago = EXCLUDED.total_30d_ago,
            last_updated = CURRENT_TIMESTAMP,
            last_total = EXCLUDED.total,
            last_active_date = %s,
            current_streak = %s
    """, (
        username,
        stats.get("ranking"),
        stats.get("reputation"),
        easy,
        medium,
        hard,
        new_total,
        total_7d_ago,
        total_30d_ago,
        new_total,
        last_active_date,
        current_streak,
        last_active_date,
        current_streak
    ))

    conn.commit()
    cursor.close()
    conn.close()

# ---------- CORE LOGIC ---------- #
def fetch_or_update_user(username, force_live=False):
    key = f"lc:{username.lower()}"

    # ✅ ONLY use cache for response, not for DB update
    if not force_live:
        cached = cache_get(key)
        if cached and cached.get("ok"):
            return cached

    try:
        # 🔥 ALWAYS fetch fresh data when updating DB
        data = fetch_leetcode(username)
        payload = transform_response(data)

        if payload.get("ok"):
            store_user_stats(username, payload)
            cache_set(key, payload)

        return payload

    except requests.Timeout:
        return {"ok": False, "error": "LeetCode API timed out."}
    except requests.RequestException as e:
        status = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
        return {"ok": False, "error": f"Network error (status={status})"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------- ADMIN ROUTES ---------- #


@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    text = request.form.get("usernames", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No usernames provided"}), 400
    usernames = [u.strip() for u in text.split("\n") if u.strip()]

    results = {"success": [], "errors": []}
    for username in usernames[:50]:
        stats = fetch_or_update_user(username)
        if stats.get("ok"):
            results["success"].append(username)
        else:
            results["errors"].append(f"{username}: {stats.get('error')}")
        time.sleep(0.8)
    return jsonify(results)


@app.route("/admin/delete/<username>", methods=["DELETE"])
def admin_delete(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM leetcode_users WHERE username = %s", (username,))
    deleted = cursor.rowcount > 0
    conn.commit()
    cursor.close()
    conn.close()
    CACHE.pop(f"lc:{username.lower()}", None)
    if deleted:
        return jsonify({"ok": True, "message": f"User '{username}' deleted successfully."})
    else:
        return jsonify({"ok": False, "error": f"User '{username}' not found."}), 404


@app.route("/admin/delete_all", methods=["DELETE"])
def admin_delete_all():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leetcode_users")
        deleted_count = cursor.rowcount if cursor.rowcount is not None else 0
        conn.commit()
        cursor.close()
        conn.close()
        for key in list(CACHE.keys()):
            if key.startswith("lc:"):
                CACHE.pop(key, None)
        return jsonify({"ok": True, "message": f"All users deleted successfully. {deleted_count} records removed."})
    except Exception as e:
        app.logger.error("Failed to delete all users: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------- REFRESH LOGIC ---------- #
_refresh_lock = threading.Lock()


def refresh_all_users_once():
    """Refresh all users sequentially from DB"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM leetcode_users ORDER BY total DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    for uname in [r[0] for r in rows]:
        try:
            CACHE.pop(f"lc:{uname.lower()}", None)
            data = fetch_leetcode(uname)
            payload = transform_response(data)
            if payload.get("ok"):
                cache_set(f"lc:{uname.lower()}", payload)
                store_user_stats(uname, payload)
            time.sleep(0.5)
        except Exception as e:
            app.logger.warning("Refresh failed for %s: %s", uname, e)


@app.route("/admin/refresh_now", methods=["POST"])
def admin_refresh_now():
    """Trigger background refresh of ALL users"""
    def _run():
        with _refresh_lock:
            try:
                refresh_all_users_once()
                app.logger.info("Manual refresh completed.")
            except Exception as e:
                app.logger.error("Manual refresh failed: %s", e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Refresh started"}), 202


def get_activity_status(last_active_date):
    if not last_active_date:
        return {
            "label": "Dormant",
            "color": "red",
            "icon": "🔴"
        }

    days_gap = (date.today() - last_active_date).days

    if days_gap <= 1:
        return {
            "label": "Active",
            "color": "green",
            "icon": "🟢"
        }
    elif days_gap <= 3:
        return {
            "label": "Inactive",
            "color": "orange",
            "icon": "🟡"
        }
    else:
        return {
            "label": "Dormant",
            "color": "red",
            "icon": "🔴"
        }

# ---------- API ROUTES ---------- #


def get_trend_status(delta):
    if delta > 0:
        return "improving"
    elif delta == 0:
        return "stagnant"
    else:
        return "declining"


@app.route("/api/users")
def api_users():
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 12))
        offset = (page - 1) * per_page
        refresh_live = request.args.get("live", "0").lower() in ("1", "true", "yes")

        conn = get_db_connection()
        cursor = conn.cursor()

        # total users count
        cursor.execute("SELECT COUNT(*) FROM leetcode_users")
        total = cursor.fetchone()[0]

        # ============================================================
        # 🔥 AUTO-REFRESH ON NORMAL PAGE LOAD (RESTORES OLD BEHAVIOR)
        # ============================================================
        if not refresh_live:
            cursor.execute("""
                SELECT username, last_updated
                FROM leetcode_users
                ORDER BY total DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))

            rows = cursor.fetchall()
            now = datetime.now(timezone.utc)

            for uname, last_updated in rows:
                # refresh if never updated OR stale (>5 minutes)
                if not last_updated or (now - last_updated).seconds > 300:
                    fetch_or_update_user(uname)
                    time.sleep(0.3)

        # ============================================================
        # 🔥 FORCE LIVE REFRESH (ADMIN / live=1)
        # ============================================================
        if refresh_live:
            cursor.execute("""
                SELECT username
                FROM leetcode_users
                ORDER BY total DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))

            rows = cursor.fetchall()
            for (uname,) in rows[:10]:
                CACHE.pop(f"lc:{uname.lower()}", None)
                fetch_or_update_user(uname, force_live=True)
                time.sleep(0.5)

        # re-open connection to get fresh data
        cursor.close()
        conn.close()
        conn = get_db_connection()
        cursor = conn.cursor()

        # ============================================================
        # FINAL DATA SELECT (DB IS NOW UP-TO-DATE)
        # ============================================================
        cursor.execute("""
            SELECT username, ranking, reputation, easy, medium, hard,
                   total,
                   total_7d_ago, total_30d_ago,
                   last_updated, current_streak, last_active_date
            FROM leetcode_users
            ORDER BY total DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))

        users = []

        for row in cursor.fetchall():
            easy = row[3] or 0
            medium = row[4] or 0
            hard = row[5] or 0

            placement_score = easy * 1 + medium * 2 + hard * 3

            if placement_score < 200:
                placement_level = "Beginner"
                level_color = "red"
            elif placement_score < 600:
                placement_level = "Intermediate"
                level_color = "orange"
            else:
                placement_level = "Placement Ready"
                level_color = "green"

            # activity + last solved
            activity = get_activity_status(row[11])

            if row[11] is None:
                last_solved_text = "Never"
            else:
                days_ago = (date.today() - row[11]).days
                if days_ago == 0:
                    last_solved_text = "Today"
                elif days_ago == 1:
                    last_solved_text = "Yesterday"
                else:
                    last_solved_text = f"{days_ago} days ago"

            # trends
            trend_7d = None
            trend_30d = None

            if row[7] is not None:
                delta_7d = row[6] - row[7]
                trend_7d = {"delta": delta_7d, "status": get_trend_status(delta_7d)}

            if row[8] is not None:
                delta_30d = row[6] - row[8]
                trend_30d = {"delta": delta_30d, "status": get_trend_status(delta_30d)}

            users.append({
                "username": row[0],
                "ranking": row[1],
                "reputation": row[2],
                "easy": easy,
                "medium": medium,
                "hard": hard,
                "total": row[6],
                "placement_score": placement_score,
                "placement_level": placement_level,
                "placement_color": level_color,
                "activity_status": activity["label"],
                "activity_color": activity["color"],
                "activity_icon": activity["icon"],
                "last_solved_text": last_solved_text,
                "user_trend": {
                    "7d": trend_7d,
                    "30d": trend_30d
                },
                "streak": row[10] or 0,
                "last_active": row[11].isoformat() if row[11] else None,
                "last_updated": row[9].isoformat() if row[9] else None,
            })

        cursor.close()
        conn.close()

        return jsonify({
            "users": users,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
            "live_refreshed": refresh_live
        })

    except Exception as e:
        app.logger.exception("api_users error")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/debug/db")
def debug_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        ok = cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({"ok": True, "msg": "Connected to database", "test": ok[0] if ok else None}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/admin")
def admin():
    return send_from_directory("static", "admin.html")


@app.route("/login")
def login():
    return send_from_directory("static", "login.html")


@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print("⚠️ init_db() failed:", e)
    print("🚀 Server running at http://127.0.0.1:5000")
    app.run(debug=True)
