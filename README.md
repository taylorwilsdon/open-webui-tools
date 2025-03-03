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

Note - for self-hosted Jira instances (Jira Server, Jira Data Center) you can use just the PAT + instance hostname. With Jira Cloud, you need to include both the username and the PAT alongside the hostname due to differences in the way they implement token auth. 

### Example API Calls

#### **Search for Issues**
llm
```
Please find all open tickets in the DEMO project
```
python
```
jira.search_issues("project = DEMO AND status = Open")
```

#### **Get Issue Details**
llm
```
Fetch information about DEMO-123
```
python
```
jira.get_issue("DEMO-123")
```

#### **Create an Issue**
llm
```
Create a new issue in the demo project with a bug report report and summary "Something is broken" with high priority
```
python
```
jira.create_issue("DEMO", "Bug Report", "Something is broken", "Bug", "High")
```

#### **Add a Comment**
llm
```
Add a comment to DEMO-123 that says "This is a new comment"
```
python
```
jira.add_comment("DEMO-123", "This is a new comment")
```

#### **Assign an Issue**
llm
```
Assign DEMO-123 to john.doe
```
python
```
jira.assign_issue("DEMO-123", "john.doe")
```

#### **Update Issue Status**
llm
```
Update DEMO-123 to the In Progress status
```
python
```
jira.update_status("DEMO-123", "In Progress")
```

#### **List Jira Projects**
llm
```
List all our Jira projects
```
python
```
jira.list_projects()
```

## 📜 License

This tool is released under the [MIT License](LICENSE). Contributions are welcome!

---

🔧 **Developed by [@taylorwilsdon](https://github.com/taylorwilsdon)**  
📂 **Repository**: [GitHub](https://github.com/taylorwilsdon/open-webui-tools)
