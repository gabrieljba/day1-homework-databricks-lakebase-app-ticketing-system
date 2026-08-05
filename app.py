"""
Internal Support Ticketing System - Databricks App
- Serves a Flask API for ticket management
- Reads/writes to Lakebase (Databricks-managed Postgres) via lakebase.py
- Allows users to create tickets, add messages, and update ticket status

Run locally:
    python app.py
Deploy as a Databricks App using app.yaml.
"""

import logging
import os
from datetime import datetime

from databricks.sdk import WorkspaceClient
from flask import Flask, jsonify, render_template, request

import lakebase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ticket-app")

app = Flask(__name__)
_w = WorkspaceClient()

TICKETS_TABLE = "tickets"
MESSAGES_TABLE = "ticket_messages"


def ensure_tickets_table():
    """Create the tickets table in Lakebase if it doesn't exist yet."""
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TICKETS_TABLE} (
            ticket_id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'resolved')),
            priority TEXT CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
            category TEXT,
            created_by TEXT NOT NULL,
            assigned_to TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    # Create indexes for common queries
    lakebase.run_write(
        f"CREATE INDEX IF NOT EXISTS idx_tickets_status ON {TICKETS_TABLE}(status)"
    )
    lakebase.run_write(
        f"CREATE INDEX IF NOT EXISTS idx_tickets_created_by ON {TICKETS_TABLE}(created_by)"
    )


def ensure_messages_table():
    """Create the ticket_messages table in Lakebase if it doesn't exist yet."""
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {MESSAGES_TABLE} (
            message_id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES {TICKETS_TABLE}(ticket_id) ON DELETE CASCADE,
            message_text TEXT NOT NULL,
            author TEXT NOT NULL,
            is_internal BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Create index for message lookups
    lakebase.run_write(
        f"CREATE INDEX IF NOT EXISTS idx_messages_ticket_id ON {MESSAGES_TABLE}(ticket_id)"
    )


def _current_user_email() -> str:
    """
    Resolve the current user's email for ticket attribution.

    Databricks Apps inject the logged-in user's identity via the
    X-Forwarded-Email header on every request. Fall back to the Databricks
    SDK's current_user API for local development where that header isn't set.
    """
    header_email = request.headers.get("X-Forwarded-Email")
    if header_email:
        return header_email
    return _w.current_user.me().user_name


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(Exception)
def handle_exception(err):
    """Ensure all unhandled errors return JSON (not an HTML error page),
    so the frontend's resp.json() call never chokes on HTML."""
    logger.exception("Unhandled exception while processing request")
    status_code = getattr(err, "code", 500)
    if not isinstance(status_code, int):
        status_code = 500
    return jsonify({"error": str(err)}), status_code


@app.route("/")
def index():
    """Render the main ticketing UI."""
    return render_template("index.html")


@app.route("/api/tickets", methods=["GET"])
def list_tickets():
    """List all tickets with optional filtering."""
    ensure_tickets_table()
    
    # Optional filters
    status = request.args.get("status")
    priority = request.args.get("priority")
    created_by = request.args.get("created_by")
    
    query = f"SELECT * FROM {TICKETS_TABLE} WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = %s"
        params.append(status)
    if priority:
        query += " AND priority = %s"
        params.append(priority)
    if created_by:
        query += " AND created_by = %s"
        params.append(created_by)
    
    query += " ORDER BY created_at DESC"
    
    rows = lakebase.run_query(query, tuple(params) if params else None)
    return jsonify(rows)


@app.route("/api/tickets/<int:ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    """Get details for a specific ticket."""
    ensure_tickets_table()
    
    rows = lakebase.run_query(
        f"SELECT * FROM {TICKETS_TABLE} WHERE ticket_id = %s",
        (ticket_id,)
    )
    
    if not rows:
        return jsonify({"error": "Ticket not found"}), 404
    
    return jsonify(rows[0])


@app.route("/api/tickets", methods=["POST"])
def create_ticket():
    """Create a new support ticket."""
    ensure_tickets_table()
    ensure_messages_table()
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.json
    title = data.get("title", "").strip()
    priority = data.get("priority", "medium")
    category = data.get("category", "").strip() or None
    initial_message = data.get("message", "").strip()
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
    
    if priority not in ["low", "medium", "high", "urgent"]:
        return jsonify({"error": "Invalid priority value"}), 400
    
    created_by = _current_user_email()
    
    # Create ticket
    rows = lakebase.run_write_returning(
        f"""
        INSERT INTO {TICKETS_TABLE} (title, status, priority, category, created_by)
        VALUES (%s, 'open', %s, %s, %s)
        RETURNING ticket_id, title, status, priority, category, created_by, created_at, updated_at
        """,
        (title, priority, category, created_by)
    )
    
    ticket = rows[0]
    
    # Add initial message if provided
    if initial_message:
        lakebase.run_write(
            f"""
            INSERT INTO {MESSAGES_TABLE} (ticket_id, message_text, author)
            VALUES (%s, %s, %s)
            """,
            (ticket["ticket_id"], initial_message, created_by)
        )
    
    return jsonify(ticket), 201


@app.route("/api/tickets/<int:ticket_id>", methods=["PUT"])
def update_ticket(ticket_id):
    """Update a ticket's status, priority, or other fields."""
    ensure_tickets_table()
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.json
    
    # First, check if the ticket is resolved (if trying to change priority)
    if "priority" in data and "status" not in data:
        # Fetch current ticket status
        current = lakebase.run_query(
            f"SELECT status FROM {TICKETS_TABLE} WHERE ticket_id = %s",
            (ticket_id,)
        )
        if current and current[0]["status"] == "resolved":
            return jsonify({"error": "Cannot change priority of a resolved ticket. Reopen the ticket first."}), 400
    
    updates = []
    params = []
    
    # Allowed fields to update
    if "status" in data:
        status = data["status"]
        if status not in ["open", "in_progress", "resolved"]:
            return jsonify({"error": "Invalid status value"}), 400
        updates.append("status = %s")
        params.append(status)
        
        # Set resolved_at timestamp when status changes to resolved
        if status == "resolved":
            updates.append("resolved_at = now()")
        elif status != "resolved":
            updates.append("resolved_at = NULL")
    
    if "priority" in data:
        priority = data["priority"]
        if priority not in ["low", "medium", "high", "urgent"]:
            return jsonify({"error": "Invalid priority value"}), 400
        updates.append("priority = %s")
        params.append(priority)
    
    if "category" in data:
        updates.append("category = %s")
        params.append(data["category"] or None)
    
    if "assigned_to" in data:
        updates.append("assigned_to = %s")
        params.append(data["assigned_to"] or None)
    
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400
    
    # Always update the updated_at timestamp
    updates.append("updated_at = now()")
    
    params.append(ticket_id)
    
    query = f"UPDATE {TICKETS_TABLE} SET {', '.join(updates)} WHERE ticket_id = %s RETURNING *"
    
    rows = lakebase.run_write_returning(query, tuple(params))
    
    if not rows:
        return jsonify({"error": "Ticket not found"}), 404
    
    return jsonify(rows[0])




@app.route("/api/tickets/<int:ticket_id>", methods=["DELETE"])
def delete_ticket(ticket_id):
    """Delete a ticket and all its messages (CASCADE)"""
    try:
        # Check if ticket exists first
        check_sql = "SELECT ticket_id FROM tickets WHERE ticket_id = %s"
        result = lakebase.run_query(check_sql, (ticket_id,))
        
        if not result:
            return jsonify({"error": "Ticket not found"}), 404
        
        # Delete the ticket (messages will be cascade deleted)
        delete_sql = "DELETE FROM tickets WHERE ticket_id = %s"
        lakebase.run_write(delete_sql, (ticket_id,))
        
        return jsonify({"message": "Ticket deleted successfully", "ticket_id": ticket_id}), 200
    
    except Exception as e:
        logger.error(f"Error deleting ticket {ticket_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/tickets/<int:ticket_id>/messages", methods=["GET"])
def get_ticket_messages(ticket_id):
    """Get all messages for a specific ticket."""
    ensure_messages_table()
    
    rows = lakebase.run_query(
        f"""
        SELECT message_id, ticket_id, message_text, author, is_internal, created_at
        FROM {MESSAGES_TABLE}
        WHERE ticket_id = %s
        ORDER BY created_at ASC
        """,
        (ticket_id,)
    )
    
    return jsonify(rows)


@app.route("/api/tickets/<int:ticket_id>/messages", methods=["POST"])
def add_ticket_message(ticket_id):
    """Add a new message to a ticket."""
    ensure_messages_table()
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.json
    message_text = data.get("message", "").strip()
    is_internal = data.get("is_internal", False)
    
    if not message_text:
        return jsonify({"error": "Message text is required"}), 400
    
    author = _current_user_email()
    
    # Add message
    rows = lakebase.run_write_returning(
        f"""
        INSERT INTO {MESSAGES_TABLE} (ticket_id, message_text, author, is_internal)
        VALUES (%s, %s, %s, %s)
        RETURNING message_id, ticket_id, message_text, author, is_internal, created_at
        """,
        (ticket_id, message_text, author, is_internal)
    )
    
    # Update ticket's updated_at timestamp
    lakebase.run_write(
        f"UPDATE {TICKETS_TABLE} SET updated_at = now() WHERE ticket_id = %s",
        (ticket_id,)
    )
    
    return jsonify(rows[0]), 201


if __name__ == '__main__':
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 8000))
    app.run(debug=True, host=host, port=port)
    print(f"Flask app running on http://{host}:{port}")