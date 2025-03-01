# Jira Agent for Open-WebUI

A comprehensive tool for interacting with Jira - search, view, create, and comment on issues with ease.

## Features

- 🔍 **Search Issues**: Use JQL or free text to search Jira issues.
- 📄 **View Issues**: Retrieve detailed information including description and comments.
- 📝 **Create Issues**: Create new Jira issues with project, type, and priority.
- 💬 **Add Comments**: Add comments to existing issues.
- 👥 **Assign Issues**: Assign Jira issues to a user or unassign them.
- 🔄 **Update Status**: Transition issues based on available statuses.
- 📂 **List Projects**: Retrieve available project details.
- 📊 **Get Issue Metadata**: Fetch available issue types and priorities.

## Usage

To use this tool, configure your Jira credentials:

- **Personal Access Token (PAT)** (Recommended)  
- **Username & Password** (If PAT is not available)  

### Example API Calls

#### **Search for Issues**
```python
jira.search_issues("project = DEMO AND status = Open")
```

#### **Get Issue Details**
```python
jira.get_issue("DEMO-123")
```

#### **Create an Issue**
```python
jira.create_issue("DEMO", "Bug Report", "Something is broken", "Bug", "High")
```

#### **Add a Comment**
```python
jira.add_comment("DEMO-123", "This is a new comment")
```

#### **Assign an Issue**
```python
jira.assign_issue("DEMO-123", "john.doe")
```

#### **Update Issue Status**
```python
jira.update_status("DEMO-123", "In Progress")
```

#### **List Jira Projects**
```python
jira.list_projects()
```

## 📜 License

This tool is released under the [MIT License](LICENSE). Contributions are welcome!

---

🔧 **Developed by [@taylorwilsdon](https://github.com/taylorwilsdon)**  
📂 **Repository**: [GitHub](https://github.com/taylorwilsdon/open-webui-tools)
