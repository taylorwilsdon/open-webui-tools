"""
title: Jira Agent for Open-WebUI
description: A comprehensive tool for interacting with Jira - search, view, create, and comment on issues with ease.
repository: https://github.com/taylorwilsdon/open-webui-tools
author: @taylorwilsdon
author_url: https://github.com/taylorwilsdon
version: 1.0.3
changelog:
  - 1.0.3: Improved date formatting, enhanced HTML content handling, better comment display
  - 1.0.2: Extensive refactor - simplified logging, fixed duplicate messages, improved formatting
  - 1.0.1: Update with PAT support
  - 1.0.0: Initial release with comprehensive Jira integration capabilities
"""

import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, List, Union
from datetime import datetime
import requests
from pydantic import BaseModel, Field, validator

# Simple logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Get logger for this module
logger = logging.getLogger("jira_tool")


class IssueFormatter:
    """Helper class to format Jira issues consistently as markdown tables"""

    @staticmethod
    def format_date(date_str: str) -> str:
        """Format a date string from Jira API to a more readable format"""
        if not date_str or date_str == "Unknown":
            return "Unknown"

        try:
            # Clean up the timezone part if it has an extra offset
            if "+00:00" in date_str and (
                "+" in date_str.split("+00:00")[1] or "-" in date_str.split("+00:00")[1]
            ):
                date_str = date_str.split("+00:00")[0] + date_str.split("+00:00")[1]

            # Parse ISO 8601 format
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

            # Format as "Mar 10, 2025 12:34 PM"
            formatted_date = dt.strftime("%b %d, %Y %I:%M %p")

            return formatted_date

        except (ValueError, TypeError) as e:
            # Log the error but don't crash
            logger.debug(f"Date parsing error: {e} for string: {date_str}")
            # If parsing fails, return the original string
            return date_str

    @staticmethod
    def format_issue_details(issue: Dict[str, Any]) -> str:
        """Format a single issue in Jira-style markdown"""
        # Define status and priority icons
        status_icon = (
            "✅"
            if issue["status"].lower() in ["done", "closed", "resolved"]
            else (
                "🔄"
                if issue["status"].lower() in ["in progress", "in review"]
                else "🆕"
            )
        )
        priority_icon = (
            "🔥"
            if issue["priority"].lower() in ["highest", "high"]
            else "⚡" if issue["priority"].lower() == "medium" else "🔽"
        )

        # Format metadata badges
        metadata_badges = (
            f"`{status_icon} {issue['status']}`  "
            f"`{priority_icon} {issue['priority']}`  "
            f"`📋 {issue['type']}`  "
            f"`🕒 {IssueFormatter.format_date(issue['created'])}`  "
            f"`🔄 {IssueFormatter.format_date(issue['updated'])}`  "
            f"`🙋 {issue['reporter']}`  "
            f"`🕵️‍♂️ {issue['assignee']}`  "
        )

        # Format the main content
        return f"## [{issue['key']}] {issue['title']}\n\n" f"{metadata_badges}\n\n"

    @staticmethod
    def format_issue_list(
        issues: List[Dict[str, Any]], total: int, displayed: int
    ) -> str:
        """Format a list of issues as a markdown table"""
        if not issues:
            return "No issues found."

        table = f"### Found {total} issues (showing {displayed})\n\n"
        table += "| Key | Summary | Status | Type | Priority | Updated |\n"
        table += "|-----|---------|--------|------|----------|--------|\n"

        for issue in issues:
            table += (
                f"| [{issue['key']}]({issue['link']}) "
                f"| {issue['summary']} "
                f"| {issue['status']} "
                f"| {issue['type']} "
                f"| {issue['priority']} "
                f"| {IssueFormatter.format_date(issue['updated'])} |\n"
            )

        return table

    @staticmethod
    def format_comments(issue_id: str, comments: List[Dict[str, Any]]) -> str:
        """Format issue comments in Jira-style markdown"""
        if not comments:
            return ""

        comment_text = f"### 💬 Comments ({len(comments)})\n\n"
        for comment in comments:
            # Handle HTML content in comments
            text = comment["text"]
            if text.startswith("<") and ">" in text:
                # Clean up HTML content for better readability
                text = text.replace("\n", " ")
                # Remove excessive whitespace
                while "  " in text:
                    text = text.replace("  ", " ")
                # Add line breaks after closing paragraph tags for better readability
                text = text.replace("</p>", "</p>\n\n")

            # Format each comment in a more visually appealing style
            comment_text += (
                f"#### Comment by {comment['author']} on {IssueFormatter.format_date(comment['created'])}\n\n"
                f"{text}\n\n"
                "<div style='border-bottom: 1px solid #ddd; margin: 15px 0;'></div>\n\n"
            )
        return comment_text


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Awaitable[None]]):
        self.event_emitter = event_emitter
        self.logger = logging.getLogger("jira_tool.emitter")

    async def emit_status(
        self, description: str, done: bool, error: bool = False
    ) -> None:
        """Emit a status event with a description and completion status."""
        if error and not done:
            raise ValueError("Error status must also be marked as done")

        icon = "✅" if done and not error else "🚫 " if error else "💬"

        try:
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
        except Exception as e:
            logger.error(f"Failed to emit status event: {str(e)}")
            raise RuntimeError(f"Failed to emit status event: {str(e)}") from e

    async def emit_message(self, content: str) -> None:
        """Emit a simple message event."""
        if not content:
            raise ValueError("Message content cannot be empty")

        try:
            await self.event_emitter({"data": {"content": content}, "type": "message"})
        except Exception as e:
            logger.error(f"Failed to emit message event: {str(e)}")
            raise RuntimeError(f"Failed to emit message event: {str(e)}") from e

    async def emit_source(
        self, name: str, url: str, content: str = "", html: bool = False
    ) -> None:
        """Emit a citation source event."""
        if not name or not url:
            raise ValueError("Source name and URL are required")

        try:
            await self.event_emitter(
                {
                    "type": "citation",
                    "data": {
                        "document": [content] if content else [],
                        "metadata": [{"source": url, "html": html}],
                        "source": {"name": name},
                    },
                }
            )
        except Exception as e:
            logger.error(f"Failed to emit source event: {str(e)}")
            raise RuntimeError(f"Failed to emit source event: {str(e)}") from e

    async def emit_table(
        self,
        headers: List[str],
        rows: List[List[Any]],
        title: Optional[str] = "Results",
    ) -> None:
        """Emit a formatted markdown table of data."""
        if not headers:
            raise ValueError("Table must have at least one header")

        if any(len(row) != len(headers) for row in rows):
            raise ValueError("All rows must have the same number of columns as headers")

        # Create markdown table
        table = (
            f"### {title}\n\n|"
            + "|".join(headers)
            + "|\n|"
            + "|".join(["---"] * len(headers))
            + "|\n"
        )

        for row in rows:
            # Convert all cells to strings and escape pipe characters
            formatted_row = [str(cell).replace("|", "\\|") for cell in row]
            table += "|" + "|".join(formatted_row) + "|\n"

        await self.emit_message(table)


class JiraApiError(Exception):
    """Exception raised for Jira API errors"""

    pass


class Jira:
    def __init__(self, username: str, password: str, base_url: str, pat: str = ""):
        self.logger = logging.getLogger("jira_tool.api")
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.pat = pat
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.pat:
            self.headers["Authorization"] = f"Bearer {self.pat}"
        self.api_version = "latest"
        self.logger.info(
            f"Initialized Jira client for {self.base_url} (API version: {self.api_version})"
        )
        self.logger.debug(f"Using {'PAT' if self.pat else 'Basic Auth'} authentication")

    def _get_auth(self):
        """Return appropriate auth tuple or None based on authentication method"""
        if self.pat:
            return None
        return (self.username, self.password)

    def _handle_response(self, response: requests.Response, operation: str):
        """Handle API response and raise appropriate exceptions"""
        if response.status_code >= 200 and response.status_code < 300:
            if not response.content:
                return {}

            try:
                return response.json()
            except json.JSONDecodeError as e:
                raise JiraApiError(f"Invalid JSON response: {str(e)}") from e

        # Create appropriate error message based on status code
        error_msg = f"Jira API error ({response.status_code}): {response.text}"
        if response.status_code == 401:
            error_msg = "Authentication failed. Please check your username and API key."
        elif response.status_code == 403:
            error_msg = "You don't have permission to perform this operation."
        elif response.status_code == 404:
            error_msg = f"Resource not found while attempting to {operation}."
        elif response.status_code == 400:
            try:
                error_details = response.json()
                error_msg = f"Bad request: {error_details.get('errorMessages', ['Unknown error'])[0]}"
            except:
                error_msg = f"Bad request: {response.text}"

        raise JiraApiError(error_msg)

    def get(self, endpoint: str, params: Dict[str, Any] = None):
        url = f"{self.base_url}/rest/api/{self.api_version}/{endpoint}"
        self.logger.info(f"GET request to {url}")
        self.logger.debug(f"Request params: {params}")

        try:
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                auth=self._get_auth(),
                timeout=30,
            )
            self.logger.debug(f"Response status: {response.status_code}")
            return self._handle_response(response, f"get {endpoint}")
        except requests.RequestException as e:
            self.logger.error(
                f"Request failed for GET {endpoint}: {str(e)}", exc_info=True
            )
            raise JiraApiError(f"Request failed: {str(e)}") from e

    def post(self, endpoint: str, data: Dict[str, Any]):
        url = f"{self.base_url}/rest/api/{self.api_version}/{endpoint}"
        self.logger.info(f"POST request to {url}")
        self.logger.debug(f"Request data: {json.dumps(data)[:1000]}")

        try:
            response = requests.post(
                url, json=data, headers=self.headers, auth=self._get_auth(), timeout=30
            )
            return self._handle_response(response, f"post to {endpoint}")
        except requests.RequestException as e:
            self.logger.error(
                f"Request failed for POST {endpoint}: {str(e)}", exc_info=True
            )
            raise JiraApiError(f"Request failed: {str(e)}") from e

    def put(self, endpoint: str, data: Dict[str, Any]):
        url = f"{self.base_url}/rest/api/{self.api_version}/{endpoint}"
        self.logger.info(f"PUT request to {url}")
        self.logger.debug(f"Request data: {json.dumps(data)[:1000]}")

        try:
            response = requests.put(
                url, json=data, headers=self.headers, auth=self._get_auth(), timeout=30
            )
            return self._handle_response(response, f"update {endpoint}")
        except requests.RequestException as e:
            self.logger.error(
                f"Request failed for PUT {endpoint}: {str(e)}", exc_info=True
            )
            raise JiraApiError(f"Request failed: {str(e)}") from e

    def get_issue(
        self,
        issue_id: str,
        fields: str = "summary,description,status,assignee,reporter,created,updated,priority,issuetype,project",
    ):
        """Get detailed information about a specific Jira issue"""
        self.logger.info(f"Getting issue details for {issue_id}")
        endpoint = f"issue/{issue_id}"

        try:
            result = self.get(
                endpoint, {"fields": fields, "expand": "renderedFields,names"}
            )

            # Debug the response structure
            self.logger.debug(f"Raw result type for {issue_id}: {type(result)}")
            if result is None:
                self.logger.error(f"API returned None result for {issue_id}")
                raise JiraApiError(f"Empty response received for issue {issue_id}")

            # Check if fields exists in result
            if "fields" not in result:
                self.logger.error(f"Missing 'fields' in response for {issue_id}")
                self.logger.debug(
                    f"Response keys: {list(result.keys()) if result else 'No keys'}"
                )
                raise JiraApiError(
                    f"Invalid response structure: missing 'fields' for issue {issue_id}"
                )

            # Create a structured issue data object with proper fallbacks
            issue_data = {
                "key": issue_id,
                "title": result["fields"].get("summary", "No summary"),
                "status": (result["fields"].get("status", {}) or {}).get(
                    "name", "Unknown"
                ),
                "type": (result["fields"].get("issuetype", {}) or {}).get(
                    "name", "Unknown"
                ),
                "project": (result["fields"].get("project", {}) or {}).get(
                    "name", "Unknown"
                ),
                "priority": (result["fields"].get("priority", {}) or {}).get(
                    "name", "Not set"
                ),
                "created": IssueFormatter.format_date(
                    result["fields"].get("created", "Unknown")
                ),
                "updated": IssueFormatter.format_date(
                    result["fields"].get("updated", "Unknown")
                ),
                "reporter": (result["fields"].get("reporter", {}) or {}).get(
                    "displayName", self.username
                ),
                "assignee": (result["fields"].get("assignee", {}) or {}).get(
                    "displayName", "Unassigned"
                ),
                "link": f"{self.base_url}/browse/{issue_id}",
            }

            # Handle description with better error checking
            description_html = None

            # Try to get rendered description
            if result.get("renderedFields") and result["renderedFields"].get(
                "description"
            ):
                description_html = result["renderedFields"]["description"]
            # If no rendered description, try raw description
            elif result["fields"].get("description"):
                description_html = f"<p>{result['fields']['description']}</p>"
            else:
                description_html = "<p><em>No description provided</em></p>"

            issue_data["description"] = description_html

            self.logger.debug(f"Successfully retrieved issue {issue_id}")
            return issue_data

        except KeyError as e:
            self.logger.error(
                f"Missing field in issue response: {str(e)}", exc_info=True
            )
            self.logger.debug(
                f"Response structure: {json.dumps(result)[:500] if result else 'None'}"
            )
            raise JiraApiError(f"Invalid response structure: missing {str(e)}") from e

    def search(self, query: str, max_results: int = 10):
        """Search for Jira issues using JQL or free text"""
        self.logger.info(f"Searching issues with query: {query}")
        endpoint = "search"

        # Determine if the query is already JQL or needs conversion
        if any(
            operator in query
            for operator in ["=", "~", ">", "<", " AND ", " OR ", " ORDER BY "]
        ):
            jql = query
            self.logger.debug("Query appears to be JQL")
        else:
            # Convert free text to JQL
            terms = query.split()
            if terms:
                cql_terms = " OR ".join([f'text ~ "{term}"' for term in terms])
            else:
                cql_terms = f'text ~ "{query}"'
            jql = cql_terms
            self.logger.debug(f"Converted free text to JQL: {jql}")

        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,issuetype,priority,updated",
        }
        raw_response = self.get(endpoint, params)

        issues = []
        for item in raw_response.get("issues", []):
            try:
                issues.append(
                    {
                        "key": item["key"],
                        "summary": item["fields"].get("summary", "No summary"),
                        "status": item["fields"]
                        .get("status", {})
                        .get("name", "Unknown"),
                        "type": item["fields"]
                        .get("issuetype", {})
                        .get("name", "Unknown"),
                        "priority": item["fields"]
                        .get("priority", {})
                        .get("name", "Not set"),
                        "updated": item["fields"].get("updated", "Unknown"),
                        "link": f"{self.base_url}/browse/{item['key']}",
                    }
                )
            except KeyError as e:
                self.logger.warning(f"Missing field in search result item: {e}")
                # Continue processing other results rather than failing completely

        return {
            "issues": issues,
            "total": raw_response.get("total", 0),
            "displayed": len(issues),
        }

    def get_projects(self):
        """Get a list of available projects"""
        self.logger.info("Getting list of projects")
        endpoint = "project"
        result = self.get(endpoint)

        projects = []
        for item in result:
            try:
                projects.append(
                    {"key": item["key"], "name": item["name"], "id": item["id"]}
                )
            except KeyError as e:
                self.logger.warning(f"Missing field in project: {e}")

        self.logger.debug(f"Retrieved {len(projects)} projects")
        return projects

    def get_issue_types(self, project_key: str = None):
        """Get available issue types, optionally filtered by project"""
        self.logger.info(
            f"Getting issue types{' for project ' + project_key if project_key else ''}"
        )

        try:
            if project_key:
                endpoint = f"project/{project_key}"
                result = self.get(endpoint)
                issue_types = result.get("issueTypes", [])
            else:
                endpoint = "issuetype"
                issue_types = self.get(endpoint)

            return [{"id": it["id"], "name": it["name"]} for it in issue_types]
        except Exception as e:
            self.logger.error(f"Error getting issue types: {str(e)}", exc_info=True)
            raise JiraApiError(f"Failed to retrieve issue types: {str(e)}") from e

    def get_priorities(self):
        """Get available priorities"""
        self.logger.info("Getting list of priorities")
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
        self.logger.info(f"Creating new issue in project {project_key}")
        endpoint = "issue"
        default_issue_type = "Task"
        if not issue_type:
            issue_type = default_issue_type
            self.logger.debug(
                f"No issue type provided, using default: {default_issue_type}"
            )

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

        self.logger.debug(f"Creating issue with data: {json.dumps(issue_data)}")
        result = self.post(endpoint, issue_data)

        return {
            "key": result["key"],
            "id": result["id"],
            "link": f"{self.base_url}/browse/{result['key']}",
        }

    def add_comment(self, issue_id: str, comment: str):
        """Add a comment to an existing issue"""
        self.logger.info(f"Adding comment to issue {issue_id}")
        endpoint = f"issue/{issue_id}/comment"

        # For Jira Data Center, try the simpler format first
        try:
            # Simple format for Jira Data Center
            comment_data = {"body": comment}
            self.logger.debug("Attempting comment with legacy format")
            result = self.post(endpoint, comment_data)
            return {
                "id": result["id"],
                "created": result["created"],
                "issue_link": f"{self.base_url}/browse/{issue_id}",
            }
        except JiraApiError as e:
            # If simple format fails, try ADF format for Jira Cloud
            if "400" in str(e):
                self.logger.info(
                    "Legacy format failed, trying Atlassian Document Format"
                )
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
            else:
                raise

    def get_comments(self, issue_id: str):
        """Get comments for an issue"""
        self.logger.info(f"Getting comments for issue {issue_id}")
        endpoint = f"issue/{issue_id}/comment"

        try:
            result = self.get(endpoint)
            self.logger.debug(f"Retrieved {len(result.get('comments', []))} comments")

            comments = []
            for comment in result.get("comments", []):
                # Handle different comment formats
                text = ""

                # Try to extract from ADF format
                if (
                    "body" in comment
                    and isinstance(comment["body"], dict)
                    and "content" in comment["body"]
                ):
                    try:
                        for content in comment["body"]["content"]:
                            if "content" in content:
                                for text_content in content["content"]:
                                    if "text" in text_content:
                                        text += text_content["text"]
                    except (KeyError, TypeError) as e:
                        self.logger.warning(f"Error parsing ADF comment: {e}")

                # Try legacy format if ADF extraction yields nothing
                if not text and isinstance(comment.get("body"), str):
                    text = comment["body"]

                # If still no text, use a placeholder
                if not text:
                    text = "[Comment format not supported]"

                comments.append(
                    {
                        "id": comment["id"],
                        "author": comment.get("author", {}).get(
                            "displayName", "Unknown"
                        ),
                        "created": comment.get("created", "Unknown"),
                        "updated": comment.get("updated", "Unknown"),
                        "text": text,
                    }
                )

            return comments
        except Exception as e:
            self.logger.error(f"Error getting comments: {str(e)}", exc_info=True)
            raise JiraApiError(f"Failed to retrieve comments: {str(e)}") from e

    def assign_issue(self, issue_id: str, assignee: str):
        """Assign an issue to a user"""
        self.logger.info(f"Assigning issue {issue_id} to {assignee or 'Unassigned'}")
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
        self.logger.info(
            f"Updating status of issue {issue_id} using {'ID' if transition_id else 'name'} {transition_id or transition_name}"
        )

        if not (transition_id or transition_name):
            raise ValueError("Either transition_id or transition_name must be provided")

        # First, get available transitions
        transitions_endpoint = f"issue/{issue_id}/transitions"
        transitions = self.get(transitions_endpoint)
        self.logger.debug(
            f"Available transitions: {', '.join([t['name'] for t in transitions.get('transitions', [])])}"
        )

        transition_to_use = None

        # Find the transition by ID or name
        if transition_id:
            for t in transitions.get("transitions", []):
                if t["id"] == transition_id:
                    transition_to_use = t["id"]
                    break
        elif transition_name:
            for t in transitions.get("transitions", []):
                if t["name"].lower() == transition_name.lower():
                    transition_to_use = t["id"]
                    break

        if not transition_to_use:
            available_transitions = ", ".join(
                [
                    f"{t['name']} (ID: {t['id']})"
                    for t in transitions.get("transitions", [])
                ]
            )
            self.logger.error(
                f"Transition {transition_id or transition_name} not found. Available: {available_transitions}"
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
        self.logger.info(f"Getting available transitions for issue {issue_id}")
        transitions_endpoint = f"issue/{issue_id}/transitions"
        transitions = self.get(transitions_endpoint)

        return [
            {"id": t["id"], "name": t["name"], "to_status": t["to"]["name"]}
            for t in transitions.get("transitions", [])
        ]


class Tools:
    def __init__(self):
        self.logger = logging.getLogger("jira_tool.tools")
        self.valves = self.Valves()

    class Valves(BaseModel):
        username: str = Field(
            "", description="Your Jira username or email (leave empty if using PAT)"
        )
        password: str = Field(
            "", description="Your Jira password (leave empty if using PAT)"
        )
        pat: str = Field(
            "",
            description="Your Jira Personal Access Token (leave empty if using username/password)",
        )
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

        @validator("pat")
        def validate_credentials(cls, v, values):
            if not v and (not values.get("username") or not values.get("password")):
                raise ValueError("Either PAT or username/password must be provided")
            return v

    def _get_jira_client(self):
        """Initialize and return a Jira client using valve values"""
        if not self.valves.base_url:
            raise ValueError(
                "Jira base URL not configured. Please provide your Jira base URL."
            )
        if not self.valves.pat and (
            not self.valves.username or not self.valves.password
        ):
            raise ValueError(
                "Jira credentials not configured. Please provide either username/password or a Personal Access Token."
            )
        return Jira(
            self.valves.username,
            self.valves.password,
            self.valves.base_url,
            self.valves.pat,
        )

    async def get_issue(
        self,
        issue_id: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: dict = {},
    ):
        """Get detailed information about a Jira issue by its ID."""
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(f"Retrieving Jira issue {issue_id}", False)
            jira = self._get_jira_client()

            try:
                # Get issue data
                issue = jira.get_issue(issue_id)

                # Format issue as markdown table
                issue_markdown = IssueFormatter.format_issue_details(issue)
                await event_emitter.emit_message(issue_markdown)

                # Add source citation
                await event_emitter.emit_source(issue["title"], issue["link"])

                # Get and format comments if any
                comments = jira.get_comments(issue_id)
                if comments:
                    comment_markdown = IssueFormatter.format_comments(
                        issue_id, comments
                    )
                    await event_emitter.emit_message(comment_markdown)

                await event_emitter.emit_status(
                    f"Successfully retrieved Jira issue {issue_id}", True
                )

                # Return nothing to avoid duplicate message
                return "Success"

            except JiraApiError as e:
                await event_emitter.emit_status(
                    f"Failed to get issue {issue_id}: {str(e)}", True, True
                )
                return None

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to get issue {issue_id}: {str(e)}", True, True
            )
            return None

    async def search_issues(
        self,
        query: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        max_results: int = 10,
        __user__: dict = {},
    ):
        """Search for Jira issues using JQL or free text."""
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(f"Searching Jira for: {query}", False)
            jira = self._get_jira_client()
            results = jira.search(query, max_results)

            if not results["issues"]:
                await event_emitter.emit_status(
                    f"No issues found matching: {query}", True
                )
                return None

            # Format results using the IssueFormatter
            table_markdown = IssueFormatter.format_issue_list(
                results["issues"], results["total"], results["displayed"]
            )
            await event_emitter.emit_message(table_markdown)

            await event_emitter.emit_status(
                f"Found {results['total']} issues matching your query", True
            )

            # Return nothing to avoid duplicate message
            return "Successfully retrieved issues"

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to search issues: {str(e)}", True, True
            )
            return None

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
        """Create a new Jira issue."""
        event_emitter = EventEmitter(__event_emitter__)

        try:
            await event_emitter.emit_status(
                f"Creating new {issue_type} in project {project_key}", False
            )

            jira = self._get_jira_client()
            result = jira.create_issue(
                project_key, summary, description, issue_type, priority
            )

            creation_time = datetime.now().strftime("%b %d, %Y %I:%M %p")

            # Format success message as a table for consistency
            success_message = f"""
### ✅ Issue Created Successfully

| Attribute | Value |
|-----------|-------|
| Key | [{result['key']}]({result['link']}) |
| Summary | {summary} |
| Type | {issue_type} |
| Project | {project_key} |
| Created | {creation_time} |
"""
            await event_emitter.emit_message(success_message)
            await event_emitter.emit_status(
                f"Successfully created issue {result['key']}", True
            )

            # Return nothing to avoid duplicate message
            return f"Successfully created issue {result['key']}"

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to create issue: {str(e)}", True, True
            )
            return None

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

            return None

        except Exception as e:
            await event_emitter.emit_status(
                f"Failed to add comment: {str(e)}", True, True
            )
            return f"Error: {str(e)}"
