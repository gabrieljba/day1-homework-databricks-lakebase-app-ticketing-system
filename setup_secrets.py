"""
One-time setup script: creates the Databricks secret scope and stores the
Lakebase connection URL. Run this locally (with the Databricks CLI configured)
or from a notebook - never commit the resulting secret value anywhere.

Usage:
    python setup_secrets.py
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
import getpass

w = WorkspaceClient()

print("Setting up Databricks secrets for Ticketing System...")
print("\nCreating 'database' secret scope...")

# Create database scope for Lakebase connection
# w.secrets.create_scope(scope="database")

print("\nYou'll need your Lakebase connection URL in this format:")
print("postgresql://<role>:<password>@<host>.database.cloud.databricks.com:5432/databricks_postgres?sslmode=require")
print("\nGet this from your Lakebase instance's connection details.\n")

w.secrets.put_secret(
    scope="database",
    key="lakebase-url",
    string_value=getpass.getpass("Paste your Lakebase connection URL: ")
)

print("\nSetting permissions...")
w.secrets.put_acl(
    scope="database",
    principal="users",
    permission=workspace.AclPermission.READ,
)

print("\n✅ Setup complete! Your Lakebase URL is now stored in the 'database/lakebase-url' secret.")
print("The ticketing app will use this secret to connect to your Lakebase instance.\n")
