"""Check literal local script paths in workflow run blocks (not shell execution)."""

from pathlib import Path
import re
import sys

import yaml


# Match literal relative paths, including script arguments to interpreters.
SCRIPT = re.compile(r"(?<![\w/.:$-])((?:\.{1,2}[/\\])?(?:[\w.-]+[/\\])+[\w.-]+\.(?:py|ps1|sh))\b")


def check(root: Path) -> list[str]:
    errors = []
    for workflow in sorted((root / '.github/workflows').glob('*.y*ml')):
        data = yaml.safe_load(workflow.read_text(encoding='utf-8'))
        workflow_dir = data.get('defaults', {}).get('run', {}).get('working-directory', '.')
        for job_name, job in data.get('jobs', {}).items():
            job_dir = job.get('defaults', {}).get('run', {}).get('working-directory', workflow_dir)
            for step in job.get('steps', []):
                directory = step.get('working-directory', job_dir)
                if '${{' in directory:
                    continue  # Dynamic paths require runtime validation.
                for match in SCRIPT.finditer(step.get('run', '')):
                    script = match.group(1).replace('\\', '/')
                    if not (root / directory / script).is_file():
                        errors.append(f'{workflow.name}: {job_name}: missing {directory}/{script}')
    return errors


if __name__ == '__main__':
    failures = check(Path(__file__).resolve().parents[1])
    print('\n'.join(failures) if failures else 'Workflow script paths exist.')
    sys.exit(bool(failures))
