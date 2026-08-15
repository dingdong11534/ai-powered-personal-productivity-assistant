"""
Controlled assistant-workspace file tools — implemented in Phase 6.

Will contain: list_files(), search_files(), read_file(), create_file(),
update_file(), all scoped to a sandboxed "Assistant Workspace" directory
(never the full filesystem), and all routed through
app.core.permissions before any write or delete.
"""
