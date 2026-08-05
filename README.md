# Internal Support Ticketing System - Databricks App

A fully-featured internal support ticketing system built as a Databricks App with Lakebase (Databricks-managed Postgres) as the operational database.

## Features

### Core Ticketing
* 🎫 **Create and Manage Tickets** - Users can create support tickets with title, priority, category, and initial message
* 💬 **Message Threading** - Add multiple messages to any ticket for back-and-forth communication
* 🔄 **Status Management** - Update ticket status (Open → In Progress → Resolved) with automatic timestamp tracking
* 🎯 **Priority Levels** - Four priority levels: Low, Medium, High, Urgent
* 👤 **User Attribution** - Automatic tracking of who created tickets and messages
* 📅 **Timestamps** - Track creation time, last update, and resolution time

### Search, Filter & Sort
* 🔍 **Search by Title** - Real-time search as you type (case-insensitive)
* 📊 **Advanced Filtering** - Filter tickets by status and priority (combined filters supported)
* 📈 **Multiple Sort Options**:
  - Newest First (default)
  - Oldest First
  - Highest Priority First (Urgent → High → Medium → Low)
  - Lowest Priority First (Low → Medium → High → Urgent)
  - Status Order (Open → In Progress → Resolved)

### Visual Enhancements
* 🎨 **Colored Status Badges** - Green (Open), Blue (In Progress), Gray (Resolved)
* 🔴 **Colored Priority Badges** - Gray (Low), Orange (Medium), Red (High), Bright Red (Urgent)
* 🌈 **Dynamic Dropdown Colors** - Status/Priority dropdowns match their badge colors

### Ticket Management
* 🗑️ **Delete Tickets** - Delete tickets with confirmation dialog (cascades to all messages)
* 🔒 **Business Rules** - Cannot change priority on resolved tickets (must reopen first)
* ✅ **Smart Panel Clearing** - Right panel clears when filtered ticket is no longer visible

## Architecture

* **Flask** web framework for the API and UI
* **Lakebase (Postgres)** for operational data storage
* **Single-page application** UI with real-time updates
* **Databricks Apps** for deployment

## Database Schema

### Tables

#### `tickets`
| Column | Type | Description |
|--------|------|-------------|
| ticket_id | SERIAL PRIMARY KEY | Auto-incrementing ticket ID |
| title | TEXT NOT NULL | Brief description of the issue |
| status | TEXT NOT NULL | Current status: 'open', 'in_progress', or 'resolved' |
| priority | TEXT | Priority level: 'low', 'medium', 'high', or 'urgent' |
| category | TEXT | Optional category (e.g., 'Technical', 'Billing') |
| created_by | TEXT NOT NULL | Email of the user who created the ticket |
| assigned_to | TEXT | Email of the assigned user (optional) |
| created_at | TIMESTAMPTZ | When the ticket was created |
| updated_at | TIMESTAMPTZ | Last update timestamp |
| resolved_at | TIMESTAMPTZ | When the ticket was marked resolved |

#### `ticket_messages`
| Column | Type | Description |
|--------|------|-------------|
| message_id | SERIAL PRIMARY KEY | Auto-incrementing message ID |
| ticket_id | INTEGER | Foreign key to tickets table |
| message_text | TEXT NOT NULL | The message content |
| author | TEXT NOT NULL | Email of the message author |
| is_internal | BOOLEAN | Whether this is an internal note (default: false) |
| created_at | TIMESTAMPTZ | When the message was created |

**Foreign Key**: `ticket_messages.ticket_id` references `tickets.ticket_id` with `ON DELETE CASCADE`

## Step-by-step Setup

### 1. Create a Lakebase Instance

1. In your Databricks workspace, go to **Catalog** (left sidebar) and select the **Lakebase** tab
2. Click **Create Lakebase instance**
   - Give it a name (e.g. `ticketing-system-db`)
   - Choose capacity/compute size appropriate for your workload
   - Click **Create** and wait for it to reach **Available** status

### 2. Create a Native Password Role

1. Open the Lakebase instance and go to **Roles & Databases** tab
2. **Enable native password authentication** if not already enabled
3. **Create a new role**:
   - Click **Add role** / **Create role**
   - Choose **Password** as the authentication method
   - Name the role (e.g. `ticketing_app`)
   - Let Databricks generate a password
4. **Copy the connection URL**. It will look like:
   ```
   postgresql://<role>:<password>@<host>.database.cloud.databricks.com:5432/databricks_postgres?sslmode=require
   ```
   Keep this URL for the next step.

### 3. Store Your Secret

Run once from a **Databricks notebook** in your workspace:

1. Create a new notebook and attach it to any running cluster
2. In a cell, run:
   ```python
   %sh python setup_secrets.py
   ```
   or open a terminal and run `python setup_secrets.py`

This prompts for your **Lakebase connection URL** and stores it as secret `database/lakebase-url`.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Run Locally (Optional)

For local development:

```bash
python app.py
```

The app will be available at `http://localhost:8000`

**Note**: For local development, you can also set the `LAKEBASE_URL` environment variable directly instead of using secrets.

### 6. Deploy as a Databricks App

#### Create a Git Folder

1. In the Databricks workspace sidebar, click **Workspace** > **Create** > **Git folder**
2. Paste the Git URL of this repository
3. Choose a folder name and click **Create Git folder**

#### Create and Deploy the App

1. Go to **Compute** > **Apps** in the sidebar
2. Click **Create app**, then choose **Custom**
3. Give the app a name (e.g. `support-ticketing`)
4. For source code location, select **Workspace files** / **Git folder** and browse to your Git folder
5. Databricks will read `app.yaml` automatically
6. Click **Deploy**

Once deployed, open the app URL from the Apps UI to access the ticketing system.

## API Endpoints

### Tickets

* **`GET /api/tickets`** - List all tickets
  - Query params: `status`, `priority`, `created_by` (optional filters)
  - Returns: Array of ticket objects

* **`GET /api/tickets/<ticket_id>`** - Get a specific ticket
  - Returns: Single ticket object

* **`POST /api/tickets`** - Create a new ticket
  - Request body:
    ```json
    {
      "title": "Cannot access dashboard",
      "priority": "high",
      "category": "Technical",
      "message": "I'm getting a 403 error when trying to access the sales dashboard."
    }
    ```
  - Returns: Created ticket object

* **`PUT /api/tickets/<ticket_id>`** - Update a ticket
  - Request body (all fields optional):
    ```json
    {
      "status": "in_progress",
      "priority": "urgent",
      "category": "Technical",
      "assigned_to": "support@company.com"
    }
    ```
  - Business Rule: Cannot change priority on resolved tickets unless status is also being updated
  - Returns: Updated ticket object

* **`DELETE /api/tickets/<ticket_id>`** - Delete a ticket
  - Deletes the ticket and all associated messages (CASCADE)
  - Returns: Success message with deleted ticket ID

### Messages

* **`GET /api/tickets/<ticket_id>/messages`** - Get all messages for a ticket
  - Returns: Array of message objects

* **`POST /api/tickets/<ticket_id>/messages`** - Add a message to a ticket
  - Request body:
    ```json
    {
      "message": "I've investigated the issue. The user needs VIEW permission on the dashboard.",
      "is_internal": false
    }
    ```
  - Returns: Created message object

### Health Check

* **`GET /healthz`** - Health check endpoint
  - Returns: `{"status": "ok"}`

## File Structure

```
.
├── app.py                 # Flask application with all API routes
├── lakebase.py           # Lakebase connection helper with transaction management
├── app.yaml              # Databricks App deployment config
├── setup_secrets.py      # One-time secret setup script
├── requirements.txt      # Python dependencies
├── reset_tables.sql      # Optional script to drop/recreate tables
├── templates/
│   └── index.html       # Single-page ticketing UI with search/filter/sort
└── README.md            # This file
```

## Usage Example

### Creating a Ticket

1. Click **+ New Ticket** button
2. Fill in the title, select priority, and optionally add a category
3. Add an initial message describing the issue
4. Click **Create Ticket**

### Viewing and Updating Tickets

1. Browse tickets in the left panel
2. Click on a ticket to view its details and message history
3. Use the colored dropdowns to update status and priority (dropdown backgrounds match badge colors)
4. Add new messages using the message input at the bottom
5. Click the **🗑️ Delete Ticket** button (top-right) to delete a ticket with confirmation

### Searching, Filtering & Sorting

* **Search**: Type in the search box to filter tickets by title in real-time
* **Filter by Status**: Use the Status dropdown (All/Open/In Progress/Resolved)
* **Filter by Priority**: Use the Priority dropdown (All/Low/Medium/High/Urgent)
* **Sort**: Choose sort order from the Sort dropdown:
  - Newest First (default)
  - Oldest First
  - Highest Priority First
  - Lowest Priority First
  - Status Order
* **Combine**: Search, filters, and sort work together

### Business Rules

* ⚠️ **Resolved Ticket Priority**: Cannot change priority on a resolved ticket unless you also change its status to reopen it
* 🗑️ **Delete Confirmation**: Deleting a ticket requires confirmation and will also delete all its messages (CASCADE)

## Technical Implementation

### Transactional Consistency

* **`run_write_returning()`** - Used for all INSERT/UPDATE operations that need to return data
  - Executes SQL with RETURNING clause
  - Commits transaction before returning results
  - Prevents foreign key violations and ensures data consistency

* **`run_write()`** - Used for DELETE operations
  - Commits transaction immediately
  - Returns affected row count

### Key Files

* **`app.py`** - Flask application with all API routes and business logic
  - Uses `run_write_returning()` for all INSERT/UPDATE/RETURNING operations (lines 183, 258, 302)
  - Uses `run_write()` for DELETE operations (line 279)
  - Enforces business rule: No priority changes on resolved tickets

* **`lakebase.py`** - Database connection helper with transaction management
  - `run_query()` - For SELECT queries
  - `run_write()` - For DELETE with commit
  - `run_write_returning()` - For INSERT/UPDATE with RETURNING and commit

* **`templates/index.html`** - Single-page application with:
  - Real-time search and filtering
  - Client-side sorting (no backend calls)
  - Dynamic dropdown coloring with persistence
  - Smart panel clearing when filtered tickets aren't visible

### Recent Bug Fixes

* ✅ **Dropdown Color Persistence** - Fixed issue where status/priority dropdown colors would briefly appear then disappear after updates. Now colors persist correctly.
* ✅ **Ghost Ticket Panel** - Fixed issue where right panel would still show a ticket after it was filtered out of the list. Panel now clears automatically.

## Enabling Change Data Feed (CDF) for Lakebase Tables

Lakebase supports **Change Data Feed (CDF)** to stream row-level changes from Postgres tables into Unity Catalog Delta tables.

### 1. Set REPLICA IDENTITY FULL

Enable full row capture for both tables:

```sql
ALTER TABLE tickets REPLICA IDENTITY FULL;
ALTER TABLE ticket_messages REPLICA IDENTITY FULL;
```

Run these commands from a SQL editor connected to your Lakebase instance.

### 2. Start CDF from the Lakebase UI

1. In your Databricks workspace, open the **Lakebase** tab for your instance
2. Go to **Lakebase CDF** and click **Start**
3. Select the `databricks_postgres` database and the `public` schema
4. Choose the Unity Catalog destination schema where history tables should land
5. Confirm to start the feed

Once running, you'll get Delta tables named `lb_tickets_history` and `lb_ticket_messages_history` in Unity Catalog, updated every ~15 seconds with all changes.

## Notes

* The app automatically creates the database schema on first run
* All users can see all tickets and update any ticket
* User identity is resolved from Databricks authentication (X-Forwarded-Email header)
* Resolved tickets are timestamped but remain visible in the system

## Troubleshooting

**Connection errors?**
* Verify your Lakebase URL secret is correct: check the `database/lakebase-url` secret
* Ensure your Lakebase instance is running
* Check that native password authentication is enabled

**Tables not created?**
* The app creates tables automatically on first request to `/api/tickets`
* Check app logs for SQL errors

**Can't see tickets?**
* Check the filter settings (Status/Priority dropdowns)
* Ensure tickets have been created

## License

This is an internal boilerplate project for demonstration purposes.
