"""
title: Jira Agent for Open-WebUI
description: A comprehensive tool for interacting with Jira - search, view, create, and comment on issues with ease.
repository: https://github.com/taylorwilsdon/open-webui-tools
author: @taylorwilsdon
author_url: https://github.com/taylorwilsdon
version: 1.0.0
changelog:
  - 1.0.0: Initial release with comprehensive Jira integration capabilities
"""

import base64
import json
import re
import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union
import requests
from pydantic import BaseModel, Field, validator


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Awaitable[None]]):
        self.event_emitter = event_emitter

    async def emit_status(self, description: str, done: bool, error: bool = False):
        icon = "✅" if done and not error else "❌" if error else "🔎"
        await self.event_emitter(
            {
                "data": {
                    "description": f"{icon} {description}",
                    "status": "complete" if done else "in_progress",
                    "done": done,
                },
                "type": "status",
            }
        )

    async def emit_message(self, content: str):
        await self.event_emitter({"data": {"content": content}, "type": "message"})

    async def emit_source(self, name: str, url: str, content: str, html: bool = False):
        await self.event_emitter(
            {
                "type": "citation",
                "data": {
                    "document": [content],
                    "metadata": [{"source": url, "html": html}],
                    "source": {"name": name},
                },
            }
        )

    async def emit_table(
        self, headers: List[str], rows: List[List[Any]], title: str = "Results"
    ):
        """Emit a formatted table of data"""
        # Create markdown table
        table = (
            f"### {title}\n\n|"
            + "|".join(headers)
            + "|\n|"
            + "|".join(["---"] * len(headers))
            + "|\n"
        )

        for row in rows:
            formatted_row = [str(cell).replace("|", "\\|") for cell in row]
            table += "|" + "|".join(formatted_row) + "|\n"

        table += "\n"

        await self.emit_message(table)


class JiraApiError(Exception):
    """Exception raised for Jira API errors"""

    pass


class Jira:
    def __init__(self, username: str, password: str, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.api_version = "latest"  # Using Jira API v3 by default

    def _handle_response(self, response: requests.Response, operation: str):
        """Handle API response and raise appropriate exceptions"""
        if response.status_code >= 200 and response.status_code < 300:
            if response.content:
                return response.json()
            return {}

        error_msg = f"Jira API error ({response.status_code}): {response.text}"
        if response.status_code == 401:
            error_msg = "Authentication failed. Please check your username and API key."
        elif response.status_code == 403:
            error_msg = "You don't have permission to perform this operation."
        elif response.status_code == 404:
            error_msg = f"Resource not found while attempting to {operation}."

        raise JiraApiError(error_msg)

    def get(self, endpoint: str, params: Dict[str, Any] = None):
        url = f"{self.base_url}/rest/api/{self.api_version}/{endpoint}"
        response = requests.get(
            url,
            params=params,
            headers=self.headers,
            auth=(self.username, self.password),
        )
        return self._handle_response(response, f"get {endpoint}")

    def post(self, endpoint: str, data: Dict[str, Any]):
        url = f"{self.base_url}/rest/api/{self.api_version}/{endpoint}"
        response = requests.post(
            url,
            json=data,
            headers=self.headers,
            auth=(self.username, self.password),
        )
        return self._handle_response(response, f"post to {endpoint}")

    def put(self, endpoint: str, data: Dict[str, Any]):
        url = f"{self.base_url}/rest/api/{self.api_version}/{endpoint}"
        response = requests.put(
            url,
            json=data,
            headers=self.headers,
            auth=(self.username, self.password),
        )
        return self._handle_response(response, f"update {endpoint}")

    def get_issue(
        self,
        issue_id: str,
        fields: str = "summary,description,status,assignee,reporter,created,updated,priority,issuetype,project",
    ):
        """Get detailed information about a specific Jira issue"""
        endpoint = f"issue/{issue_id}"
        result = self.get(
            endpoint, {"fields": fields, "expand": "renderedFields,names"}
        )

        issue_data = {
            "key": issue_id,
            "title": result["fields"]["summary"],
            "status": result["fields"]["status"]["name"],
            "type": result["fields"]["issuetype"]["name"],
            "project": result["fields"]["project"]["name"],
            "priority": result["fields"].get("priority", {}).get("name", "Not set"),
            "created": result["fields"].get("created", "Unknown"),
            "updated": result["fields"].get("updated", "Unknown"),
            "reporter": result["fields"]
            .get("reporter", {})
            .get("displayName", self.username),
            "assignee": result["fields"]
            .get("assignee", {})
            .get("displayName", "Unassigned"),
            "link": f"{self.base_url}/browse/{issue_id}",
        }

        # Handle description - might be None for some tickets
        if result["renderedFields"].get("description"):
            issue_data["description"] = result["renderedFields"]["description"]
        else:
            issue_data["description"] = "<p><em>No description provided</em></p>"

        return issue_data

    def search(self, query: str, max_results: int = 10):
        """Search for Jira issues using JQL or free text"""
        endpoint = "search"

        # Determine if the query is already JQL or needs conversion
        if any(
            operator in query
            for operator in ["=", "~", ">", "<", " AND ", " OR ", " ORDER BY "]
        ):
            jql = query
        else:
            # Convert free text to JQL
            terms = query.split()
            if terms:
                cql_terms = " OR ".join([f'text ~ "{term}"' for term in terms])
            else:
                cql_terms = f'text ~ "{query}"'
            jql = cql_terms

        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,issuetype,priority,updated",
        }
        raw_response = self.get(endpoint, params)

        issues = []
        for item in raw_response["issues"]:
            issues.append(
                {
                    "key": item["key"],
                    "summary": item["fields"]["summary"],
                    "status": item["fields"]["status"]["name"],
                    "type": item["fields"]["issuetype"]["name"],
                    "priority": item["fields"]
                    .get("priority", {})
                    .get("name", "Not set"),
                    "updated": item["fields"].get("updated", "Unknown"),
                    "link": f"{self.base_url}/browse/{item['key']}",
                }
            )

        return {
            "issues": issues,
            "total": raw_response["total"],
            "displayed": len(issues),
        }

    def get_projects(self):
        """Get a list of available projects"""
        endpoint = "project"
        result = self.get(endpoint)

        projects = []
        for item in result:
            projects.append(
                {"key": item["key"], "name": item["name"], "id": item["id"]}
            )

        return projects

    def get_issue_types(self, project_key: str = None):
        """Get available issue types, optionally filtered by project"""
        if project_key:
            endpoint = f"project/{project_key}"
            result = self.get(endpoint)
            issue_types = result.get("issueTypes", [])
        else:
            endpoint = "issuetype"
            issue_types = self.get(endpoint)

        return [{"id": it["id"], "name": it["name"]} for it in issue_types]

    def get_priorities(self):
        """Get available priorities"""
        endpoint = "priority"
        priorities = self.get(endpoint)
        return [{"id": p["id"], "name": p["name"]} for p in priorities]

    def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
        priority: str = None,
    ):
        """Create a new Jira issue"""
        endpoint = "issue"
        default_issue_type = "Task"
        if not issue_type:
            issue_type = default_issue_type
        # Build the issue fields
        issue_data = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
            }
        }

        # Add priority if specified
        if priority:
            issue_data["fields"]["priority"] = {"name": priority}

        result = self.post(endpoint, issue_data)

        return {
            "key": result["key"],
            "id": result["id"],
            "link": f"{self.base_url}/browse/{result['key']}",
        }

    def add_comment(self, issue_id: str, comment: str):
        """Add a comment to an existing issue"""
        endpoint = f"issue/{issue_id}/comment"

        comment_data = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment}],
                    }
                ],
            }
        }

        result = self.post(endpoint, comment_data)

        return {
            "id": result["id"],
            "created": result["created"],
            "issue_link": f"{self.base_url}/browse/{issue_id}",
        }

    def get_comments(self, issue_id: str):
        """Get comments for an issue"""
        endpoint = f"issue/{issue_id}/comment"
        result = self.get(endpoint)

        comments = []
        for comment in result.get("comments", []):
            # Extract text from the document structure
            text = ""
            if "body" in comment and "content" in comment["body"]:
                for content in comment["body"]["content"]:
                    if "content" in content:
                        for text_content in content["content"]:
                            if "text" in text_content:
                                text += text_content["text"]

            comments.append(
                {
                    "id": comment["id"],
                    "author": comment.get("author", {}).get("displayName", "Unknown"),
                    "created": comment.get("created", "Unknown"),
                    "updated": comment.get("updated", "Unknown"),
                    "text": text,
                }
            )

        return comments

    def assign_issue(self, issue_id: str, assignee: str):
        """Assign an issue to a user"""
        endpoint = f"issue/{issue_id}/assignee"

        # Handle special case for unassigning
        if not assignee or assignee.lower() in ["unassigned", "none"]:
            data = {"assignee": None}
        else:
            data = {"assignee": {"name": assignee}}

        self.put(endpoint, data)

        return {
            "issue_key": issue_id,
            "assignee": assignee or "Unassigned",
            "link": f"{self.base_url}/browse/{issue_id}",
        }

    def update_issue_status(
        self, issue_id: str, transition_id=None, transition_name=None
    ):
        """
        Update the status of an issue using either transition ID or name
        """
        if not (transition_id or transition_name):
            raise ValueError("Either transition_id or transition_name must be provided")

        # First, get available transitions
        transitions_endpoint = f"issue/{issue_id}/transitions"
        transitions = self.get(transitions_endpoint)

        transition_to_use = None

        # Find the transition by ID or name
        if transition_id:
            for t in transitions["transitions"]:
                if t["id"] == transition_id:
                    transition_to_use = t["id"]
                    break
        elif transition_name:
            for t in transitions["transitions"]:
                if t["name"].lower() == transition_name.lower():
                    transition_to_use = t["id"]
                    break

        if not transition_to_use:
            available_transitions = ", ".join(
                [f"{t['name']} (ID: {t['id']})" for t in transitions["transitions"]]
            )
            raise JiraApiError(
                f"Transition not found. Available transitions: {available_transitions}"
            )

        # Perform the transition
        transition_data = {"transition": {"id": transition_to_use}}
        self.post(f"issue/{issue_id}/transitions", transition_data)

        # Get updated issue to confirm new status
        updated_issue = self.get_issue(issue_id, "status")

        return {
            "issue_key": issue_id,
            "new_status": updated_issue["status"],
            "link": f"{self.base_url}/browse/{issue_id}",
        }

    def get_available_transitions(self, issue_id: str):
        """Get available status transitions for an issue"""
        transitions_endpoint = f"issue/{issue_id}/transitions"
        transitions = self.get(transitions_endpoint)

        return [
            {"id": t["id"], "name": t["name"], "to_status": t["to"]["name"]}
            for t in transitions["transitions"]
        ]


class Tools:
    def __init__(self):
        self.valves = self.Valves()

    class Valves(BaseModel):
        username: str = Field("", description="Your Jira username or email")
        password: str = Field("", description="Your Jira password")
        base_url: str = Field(
            "",
            description="Your Jira base URL (e.g., https://your-company.atlassian.net)",
        )

        @validator("base_url")
        def validate_url(cls, v):
            if not v:
                return v
            if not v.startswith(("http://", "https://")):
                raise ValueError("URL must start with http:// or https://")
            return v

    def _get_jira_client(self):
        """Initialize and return a Jira client using valve values"""
        if (
            not self.valves.username
            or not self.valves.password
            or not self.valves.base_url
        ):
            raise ValueError(
                "Jira credentials not configured. Please provide your username, API key, and base URL."
            )
        return Jira(self.valves.username, self.valves.password, self.valves.base_url)

    async def get_issue(
        self,
        issue_id: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: dict = {},
    ):
        """
        Get detailed information about a Jira issue by its ID.

        :param issue_id: The ID of the issue (e.g., PROJECT-123)
        :return: Comprehensive issue details including title, status, description, and more
        """
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(f"Retrieving Jira issue {issue_id}", False)

            jira = self._get_jira_client()
            issue = jira.get_issue(issue_id)

            # Format and emit issue information
            issue_card = f"""
### 🎫 {issue['key']}: {issue['title']}

**Status:** {issue['status']}  
**Type:** {issue['type']}  
**Priority:** {issue['priority']}  
**Project:** {issue['project']}  

**Created:** {issue['created']}  
**Updated:** {issue['updated']}  
**Reporter:** {issue['reporter']}  
**Assignee:** {issue['assignee']}  

**Link:** [{issue['key']}]({issue['link']})
"""
            await event_emitter.emit_message(issue_card)
            await event_emitter.emit_source(
                f"Description of {issue['key']}",
                issue["link"],
                issue["description"],
                True,
            )

            # Get comments
            comments = jira.get_comments(issue_id)
            if comments:
                comment_text = f"### 💬 Comments on {issue_id} ({len(comments)})\n\n"
                for i, comment in enumerate(comments):
                    comment_text += f"**{i+1}. {comment['author']}** - {comment['created']}\n{comment['text']}\n\n"
                await event_emitter.emit_message(comment_text)

            await event_emitter.emit_status(
                f"Successfully retrieved Jira issue {issue_id}", True
            )
            return json.dumps(issue)

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to get issue {issue_id}: {str(e)}", True, True
            )
            return f"Error: {str(e)}"

    async def search_issues(
        self,
        query: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        max_results: int = 10,
        __user__: dict = {},
    ):
        """
        Search for Jira issues using JQL or free text.

        :param query: JQL query string or free text search
                     (e.g., "project = DEMO AND status = Open", or "login bug")
        :param max_results: Maximum number of results to return (default: 10)
        :return: List of matching issues
        """
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(f"Searching Jira for: {query}", False)

            jira = self._get_jira_client()
            results = jira.search(query, max_results)

            if not results["issues"]:
                await event_emitter.emit_status(
                    f"No issues found matching: {query}", True
                )
                return json.dumps({"message": "No issues found", "total": 0})

            # Format results as a table
            headers = ["Key", "Summary", "Status", "Type", "Priority", "Updated"]
            rows = []
            for issue in results["issues"]:
                rows.append(
                    [
                        f"[{issue['key']}]({issue['link']})",
                        issue["summary"],
                        issue["status"],
                        issue["type"],
                        issue["priority"],
                        issue["updated"],
                    ]
                )

            await event_emitter.emit_table(
                headers,
                rows,
                f"Found {results['total']} issues (showing {results['displayed']})",
            )

            await event_emitter.emit_status(
                f"Found {results['total']} issues matching your query", True
            )

            return json.dumps(results)

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to search issues: {str(e)}", True, True
            )
            return f"Error: {str(e)}"

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        issue_type: str = "Task",
        priority: str = None,
        __user__: dict = {},
    ):
        """
        Create a new Jira issue.

        :param project_key: The project key (e.g., DEMO)
        :param summary: The issue summary/title
        :param description: The issue description
        :param issue_type: The type of issue (e.g., Bug, Task, Story)
        :param priority: The priority level (e.g., High, Medium, Low)
        :return: Details of the created issue
        """
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(
                f"Creating new {issue_type} in project {project_key}", False
            )

            jira = self._get_jira_client()
            result = jira.create_issue(
                project_key, summary, description, issue_type, priority
            )

            # Get full issue details to return
            print(result)
            success_message = f"""
### ✅ Issue Created Successfully

**Key:** {result['key']}
**Summary:** {summary}  
**Type:** {issue_type}  
**Project:** {project_key}  
                """
            await event_emitter.emit_message(success_message)
            await event_emitter.emit_status(
                f"Successfully created issue {result['key']}", True
            )

            return success_message

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to create issue: {str(e)}", True, True
            )
            return f"Error: {str(e)}"

    async def add_comment(
        self,
        issue_id: str,
        comment: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: dict = {},
    ):
        """
        Add a comment to an existing Jira issue.

        :param issue_id: The ID of the issue (e.g., PROJECT-123)
        :param comment: The comment text to add
        :return: Comment details
        """
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(f"Adding comment to {issue_id}", False)

            jira = self._get_jira_client()
            result = jira.add_comment(issue_id, comment)

            confirmation = f"""
### 💬 Comment Added

Successfully added a comment to [{issue_id}]({result['issue_link']}).  
**Added at:** {result['created']}
"""
            await event_emitter.emit_message(confirmation)
            await event_emitter.emit_status(f"Comment added to {issue_id}", True)

            return json.dumps(result)

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to add comment: {str(e)}", True, True
            )
            return f"Error: {str(e)}"

    async def assign_issue(
        self,
        issue_id: str,
        assignee: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: dict = {},
    ):
        """
        Assign a Jira issue to a user.

        :param issue_id: The ID of the issue (e.g., PROJECT-123)
        :param assignee: Username of the assignee (use "Unassigned" to unassign)
        :return: Assignment details
        """
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(
                f"Assigning {issue_id} to {assignee}", False
            )

            jira = self._get_jira_client()
            result = jira.assign_issue(issue_id, assignee)

            confirmation = f"""
### 👤 Issue Assignment Updated

Issue [{issue_id}]({result['link']}) has been assigned to **{result['assignee']}**.
"""
            await event_emitter.emit_message(confirmation)
            await event_emitter.emit_status(f"Successfully assigned {issue_id}", True)

            return json.dumps(result)

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to assign issue: {str(e)}", True, True
            )
            return f"Error: {str(e)}"

    async def update_status(
        self,
        issue_id: str,
        status: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: dict = {},
    ):
        """
        Update the status of a Jira issue.

        :param issue_id: The ID of the issue (e.g., PROJECT-123)
        :param status: The new status or transition name (e.g., "In Progress", "Done")
        :return: Updated status details
        """
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(
                f"Updating {issue_id} status to '{status}'", False
            )

            jira = self._get_jira_client()

            # Get available transitions first
            await event_emitter.emit_status(
                f"Checking available transitions for {issue_id}", False
            )
            transitions = jira.get_available_transitions(issue_id)

            # Try to find transition by name
            result = jira.update_issue_status(issue_id, transition_name=status)

            confirmation = f"""
### 🔄 Issue Status Updated

Issue [{issue_id}]({result['link']}) status has been changed to **{result['new_status']}**.
"""
            await event_emitter.emit_message(confirmation)
            await event_emitter.emit_status(
                f"Successfully updated {issue_id} status", True
            )

            return json.dumps(result)

        except Exception as e:
            error_message = str(e)
            await event_emitter.emit_status(
                f"Failed to update status: {error_message}", True, True
            )
            return f"Error: {error_message}"

    async def list_projects(
        self,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: dict = {},
    ):
        """
        List available Jira projects.

        :return: List of projects with their keys and names
        """
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status("Retrieving Jira projects", False)

            jira = self._get_jira_client()
            projects = jira.get_projects()

            # Format as table
            headers = ["Key", "Name", "ID"]
            rows = [[p["key"], p["name"], p["id"]] for p in projects]

            await event_emitter.emit_table(
                headers, rows, f"Available Jira Projects ({len(projects)})"
            )
            await event_emitter.emit_status(f"Retrieved {len(projects)} projects", True)

            return json.dumps(projects)

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to list projects: {str(e)}", True, True
            )
            return f"Error: {str(e)}"

    async def get_issue_metadata(
        self,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        project_key: str = None,
        __user__: dict = {},
    ):
        """
        Get metadata for issue creation (issue types, priorities).

        :param project_key: Optional project key to get specific issue types
        :return: Available issue types and priorities
        """
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status("Retrieving Jira metadata", False)

            jira = self._get_jira_client()

            # Get issue types
            issue_types = jira.get_issue_types(project_key)

            # Get priorities
            priorities = jira.get_priorities()

            # Format as tables
            await event_emitter.emit_table(
                ["ID", "Name"],
                [[t["id"], t["name"]] for t in issue_types],
                f"Available Issue Types{' for ' + project_key if project_key else ''}",
            )

            await event_emitter.emit_table(
                ["ID", "Name"],
                [[p["id"], p["name"]] for p in priorities],
                "Available Priorities",
            )

            await event_emitter.emit_status("Successfully retrieved metadata", True)

            return json.dumps({"issue_types": issue_types, "priorities": priorities})

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to get metadata: {str(e)}", True, True
            )
            return f"Error: {str(e)}"

