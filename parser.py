import yaml
from pathlib import Path, PurePosixPath


def load_repository_config(repo_name: str):
    """Load the path-parsing configuration for a repository."""

    config_path = (
        Path(__file__).parent
        / "config"
        / "repositories"
        / f"{repo_name}.yml"
    )

    with open(config_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def parse_changed_path(path: str, repo_name: str = "tme-config"):
    """
    Parse a changed GitHub file path using repository-specific YAML rules.

    Mandatory: service, environment, billing_team, filename.
    Optional: region, when the selected pattern includes it.
    """

    config = load_repository_config(repo_name)

    # Normalize the path before parsing.
    parts = PurePosixPath(
        (path or "").replace("\\", "/").lstrip("/")
    ).parts

    # Try each configured pattern.
    for pattern in config.get("path_patterns", []):

        expected_parts = pattern["segments"]
        root = pattern.get("root")

        # If this pattern defines a root, verify and remove it.
        candidate_parts = parts

        if root:
            if not candidate_parts or candidate_parts[0] != root:
                continue

            candidate_parts = candidate_parts[1:]


        excluded_roots = pattern.get("exclude_roots", [])
        if candidate_parts and candidate_parts[0] in excluded_roots:
                continue

        # The number of path segments must match exactly.
        if len(candidate_parts) != len(expected_parts):
            continue

        # Map each path segment to its configured field name.
        extracted = dict(zip(expected_parts, candidate_parts))

        # Mandatory dimensions must be present.
        mandatory = ("service", "environment", "billing_team", "filename")

        if any(not extracted.get(field) for field in mandatory):
            continue
        # Validate the environment against configured values.
        valid_environments = config.get("validation", {}).get("environments", [])

        if extracted["environment"].lower() not in [
            env.lower() for env in valid_environments
        ]:
            continue

        # Extract the application name from the filename.
        # Identify the billing team first.
        billing_team = extracted["billing_team"]

        internal_teams = config.get("classification", {}).get(
            "internal_billing_teams", []
        )

        is_internal = billing_team.upper() in [
            team.upper() for team in internal_teams
        ]

        # Internal billing teams are grouped under one application.
        if is_internal:
            application = "internal"
        else:
            application = Path(extracted["filename"]).stem
            application = (
                application.replace("_", " ")
                .replace("-", " ")
                .strip()
                .lower()
            )

        # Classify the service type.
        service_type = (
            "internal"
            if is_internal
            else config.get("classification", {}).get("default", "external")
        )

        return {
            "service": extracted["service"].lower(),
            "environment": extracted["environment"].lower(),
            "region": extracted.get("region", "").lower() or None,
            "billing_team": billing_team.lower(),
            "service_type": service_type,
            "application": application,
            "path": "/".join(parts),
            "parse_status": "matched",
            "matched_pattern": pattern["name"]
        }

    # No configured pattern matched this path.
    return None