#!/usr/bin/env python3
"""gh-board: the only code that knows the Personal Engineering board's GraphQL shape.

  gh-board items [--status S] [--label L] [--unassigned] [--repo owner/name]   JSON lines
  gh-board field <issue-ref> <FieldName>                                        JSON scalar
  gh-board status <issue-ref> <StatusName>        add to board if missing, then set Status
  gh-board add <issue-ref>                        add to board (Status=Backlog) if missing

<issue-ref>: #42 (repo from $GH_REPO or the git cwd), owner/repo#42, or an issue URL.
Env: BOARD_OWNER (default francis-infotrack), BOARD_TITLE (default "Personal Engineering").
The project is resolved by TITLE, never by number, so a recreated board fails loudly instead
of silently no-opping.
"""
import argparse
import json
import os
import re
import subprocess
import sys


class BoardError(Exception):
    pass


def gh(*args):
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise BoardError(f"gh {' '.join(args[:2])} failed: {proc.stderr.strip()}")
    return proc.stdout


def graphql(query, **variables):
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-f", f"{key}={value}"]
    data = json.loads(gh(*args))
    if data.get("errors"):
        raise BoardError(json.dumps(data["errors"]))
    return data["data"]


_REF = re.compile(
    r"^(?:https://github\.com/(?P<uo>[^/]+)/(?P<ur>[^/]+)/issues/(?P<un>\d+)/?"
    r"|(?P<so>[^/#\s]+)/(?P<sr>[^/#\s]+)#(?P<sn>\d+)"
    r"|#?(?P<bn>\d+))$"
)


def parse_ref(ref, default_repo=None):
    """Return (owner/repo, number) for an issue URL, owner/repo#n, #n, or n."""
    m = _REF.match(ref.strip())
    if not m:
        raise BoardError(f"unrecognised issue ref: {ref!r}")
    if m.group("un"):
        return f"{m.group('uo')}/{m.group('ur')}", int(m.group("un"))
    if m.group("sn"):
        return f"{m.group('so')}/{m.group('sr')}", int(m.group("sn"))
    repo = default_repo or os.environ.get("GH_REPO") or current_repo()
    return repo, int(m.group("bn"))


def current_repo():
    return gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner").strip()


PROJECT_QUERY = """
query($login: String!) {
  user(login: $login) {
    projectsV2(first: 50) {
      nodes {
        id title
        fields(first: 30) {
          nodes { ... on ProjectV2SingleSelectField { id name options { id name } } }
        }
      }
    }
  }
}"""


def project():
    owner = os.environ.get("BOARD_OWNER", "francis-infotrack")
    title = os.environ.get("BOARD_TITLE", "Personal Engineering")
    for node in graphql(PROJECT_QUERY, login=owner)["user"]["projectsV2"]["nodes"]:
        if node["title"] == title:
            fields = {f["name"]: f for f in node["fields"]["nodes"] if f}
            return {"id": node["id"], "title": title, "fields": fields}
    raise BoardError(f"no project titled {title!r} for {owner}")


def option_id(proj, field_name, option_name):
    field = proj["fields"].get(field_name)
    if not field:
        raise BoardError(f"project {proj['title']!r} has no single-select field {field_name!r}")
    for option in field["options"]:
        if option["name"] == option_name:
            return field["id"], option["id"]
    raise BoardError(f"field {field_name!r} has no option {option_name!r}")


ITEMS_QUERY = """
query($project: ID!, $after: String) {
  node(id: $project) {
    ... on ProjectV2 {
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name field { ... on ProjectV2SingleSelectField { name } }
              }
            }
          }
          content {
            ... on Issue {
              id number title url createdAt
              repository { nameWithOwner }
              labels(first: 50) { nodes { name } }
              assignees(first: 10) { nodes { login } }
            }
          }
        }
      }
    }
  }
}"""


def flatten_item(node):
    content = node.get("content") or {}
    if "number" not in content:
        return None  # pull requests and draft items are not tickets
    values = {v["field"]["name"]: v["name"] for v in node["fieldValues"]["nodes"] if v}
    return {
        "item_id": node["id"],
        "issue_id": content["id"],
        "repo": content["repository"]["nameWithOwner"],
        "number": content["number"],
        "url": content["url"],
        "title": content["title"],
        "created_at": content["createdAt"],
        "status": values.get("Status"),
        "priority": values.get("Priority"),
        "effort": values.get("Effort"),
        "labels": [l["name"] for l in content["labels"]["nodes"]],
        "assignees": [a["login"] for a in content["assignees"]["nodes"]],
    }


def items(proj):
    """Every issue on the board. Paginates the project node directly: one connection, one cursor."""
    out, after = [], None
    while True:
        variables = {"project": proj["id"]}
        if after:
            variables["after"] = after
        page = graphql(ITEMS_QUERY, **variables)["node"]["items"]
        out.extend(item for item in map(flatten_item, page["nodes"]) if item)
        if not page["pageInfo"]["hasNextPage"]:
            return out
        after = page["pageInfo"]["endCursor"]


def filter_items(all_items, status=None, label=None, unassigned=False, repo=None):
    def keep(item):
        if status and item["status"] != status:
            return False
        if label and label not in item["labels"]:
            return False
        if unassigned and item["assignees"]:
            return False
        if repo and item["repo"] != repo:
            return False
        return True

    return [i for i in all_items if keep(i)]


def find_item(proj, repo, number):
    return next((i for i in items(proj) if i["repo"] == repo and i["number"] == number), None)


def issue_node_id(repo, number):
    return gh("api", f"repos/{repo}/issues/{number}", "--jq", ".node_id").strip()


ADD_MUTATION = """
mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
}"""

SET_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project, itemId: $item, fieldId: $field, value: { singleSelectOptionId: $option }
  }) { projectV2Item { id } }
}"""


def ensure_item(proj, repo, number):
    """addProjectV2ItemById is idempotent: an issue already on the board returns its item id."""
    data = graphql(ADD_MUTATION, project=proj["id"], content=issue_node_id(repo, number))
    return data["addProjectV2ItemById"]["item"]["id"]


def set_single_select(proj, item_id, field_name, option_name):
    field_id, opt = option_id(proj, field_name, option_name)
    graphql(SET_MUTATION, project=proj["id"], item=item_id, field=field_id, option=opt)


def cmd_items(args):
    for item in filter_items(items(project()), args.status, args.label, args.unassigned, args.repo):
        print(json.dumps(item))


def cmd_field(args):
    repo, number = parse_ref(args.ref)
    item = find_item(project(), repo, number)
    print(json.dumps(item.get(args.field.lower()) if item else None))


def cmd_status(args):
    repo, number = parse_ref(args.ref)
    proj = project()
    set_single_select(proj, ensure_item(proj, repo, number), "Status", args.name)
    print(json.dumps({"repo": repo, "number": number, "status": args.name}))


def cmd_add(args):
    repo, number = parse_ref(args.ref)
    proj = project()
    existing = find_item(proj, repo, number)
    if existing:
        print(json.dumps({"repo": repo, "number": number, "added": False, "status": existing["status"]}))
        return
    set_single_select(proj, ensure_item(proj, repo, number), "Status", "Backlog")
    print(json.dumps({"repo": repo, "number": number, "added": True, "status": "Backlog"}))


def build_parser():
    parser = argparse.ArgumentParser(prog="gh-board", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("items")
    p.add_argument("--status")
    p.add_argument("--label")
    p.add_argument("--unassigned", action="store_true")
    p.add_argument("--repo")
    p.set_defaults(func=cmd_items)
    p = sub.add_parser("field")
    p.add_argument("ref")
    p.add_argument("field")
    p.set_defaults(func=cmd_field)
    p = sub.add_parser("status")
    p.add_argument("ref")
    p.add_argument("name")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("add")
    p.add_argument("ref")
    p.set_defaults(func=cmd_add)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except BoardError as e:
        sys.exit(f"gh-board: {e}")


if __name__ == "__main__":
    main()
