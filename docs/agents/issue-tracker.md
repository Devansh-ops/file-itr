# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI through PowerShell for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body-file <path>`. Write multiline bodies to a UTF-8 Markdown file first.
- **Read an issue**: `gh issue view <number> --comments`, also fetching labels when needed.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments`.
- **Comment on an issue**: `gh issue comment <number> --body-file <path>`.
- **Apply/remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`.
- **Close**: `gh issue close <number> --comment "..."`.

Infer the repository from `git remote -v`. The writable `origin` is `Devansh-ops/file-itr`; `upstream` is `shivprime94/file-itr`.

## Pull requests as a triage surface

**PRs as a request surface: no.**

When enabled later, PRs run through the same labels and states as issues using the `gh pr` equivalents.

GitHub shares one number space across issues and PRs, so resolve an ambiguous `#42` with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `Devansh-ops/file-itr`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is one issue with child issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`.
- **Child ticket**: an issue linked as a GitHub sub-issue. Where sub-issues are unavailable, add the child to a task list and put `Part of #<map>` in its body.
- **Blocking**: use GitHub's native issue dependencies. Where unavailable, use a `Blocked by: #<n>` line.
- **Frontier**: open, unassigned child issues whose blockers are closed.
- **Claim**: `gh issue edit <n> --add-assignee @me`.
- **Resolve**: comment with the answer, close the issue, and add a context pointer to the map.
