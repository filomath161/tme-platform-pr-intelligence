import re
from pathlib import PurePosixPath

PATTERN = re.compile(r'^(?P<env>[A-Za-z0-9-]+)_(?P<app>.+?)_config\.ya?ml$', re.I)

def parse_changed_path(path: str):
    """Parse service/environment/environment_application_config.yml paths."""
    parts = PurePosixPath((path or '').replace('\\', '/').lstrip('/')).parts
    for i in range(len(parts) - 2):
        service, environment, filename = parts[i:i+3]
        match = PATTERN.match(filename)
        if match and match.group('env').lower() == environment.lower():
            app = match.group('app').replace('_', ' ').replace('-', ' ').strip().lower()
            return {'service': service.lower(), 'environment': environment.lower(), 'application': app, 'path': '/'.join(parts)}
    return None
