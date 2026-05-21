"""
Pipeline Templates — generates CI/CD pipeline definitions for automated migration.

Creates Azure DevOps YAML and GitHub Actions workflow files for running
the migration pipeline in CI/CD.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PipelineTemplates:
    """Generate CI/CD pipeline templates for migration automation."""

    def generate_github_actions(
        self,
        server_url: str,
        phases: list[str] | None = None,
        cron_schedule: str = "",
    ) -> str:
        """Generate a GitHub Actions workflow YAML.

        Args:
            server_url: PBIRS server URL.
            phases: migration phases to run (default: all).
            cron_schedule: optional cron expression for scheduled runs.
        """
        phase_list = phases or ["assessment", "export", "conversion", "import", "validation"]
        phase_str = " ".join(phase_list)

        schedule_block = ""
        if cron_schedule:
            schedule_block = f"""
  schedule:
    - cron: '{cron_schedule}'"""

        yaml = f"""name: PBIRS to PBI Online Migration

on:
  workflow_dispatch:
    inputs:
      phase:
        description: 'Migration phase to run'
        required: false
        default: 'all'
        type: choice
        options:
          - all
          - assessment
          - export
          - conversion
          - import
          - validation
      dry_run:
        description: 'Dry run mode'
        required: false
        default: 'false'
        type: boolean{schedule_block}

env:
  PBIRS_SERVER: {server_url}
  PYTHON_VERSION: '3.12'

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{{{ env.PYTHON_VERSION }}}}

      - name: Run migration
        env:
          PBI_CLIENT_ID: ${{{{ secrets.PBI_CLIENT_ID }}}}
          PBI_CLIENT_SECRET: ${{{{ secrets.PBI_CLIENT_SECRET }}}}
          PBI_TENANT_ID: ${{{{ secrets.PBI_TENANT_ID }}}}
        run: |
          python migrate.py \\
            --server ${{{{ env.PBIRS_SERVER }}}} \\
            --phase ${{{{ github.event.inputs.phase || 'all' }}}} \\
            --output ./artifacts \\
            ${{{{ github.event.inputs.dry_run == 'true' && '--dry-run' || '' }}}}

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: migration-artifacts
          path: ./artifacts/
          retention-days: 30
"""
        logger.info("Generated GitHub Actions workflow")
        return yaml

    def generate_azure_devops(
        self,
        server_url: str,
        phases: list[str] | None = None,
        cron_schedule: str = "",
    ) -> str:
        """Generate an Azure DevOps pipeline YAML.

        Args:
            server_url: PBIRS server URL.
            phases: migration phases to run.
            cron_schedule: optional cron expression.
        """
        phase_list = phases or ["assessment", "export", "conversion", "import", "validation"]

        schedule_block = ""
        if cron_schedule:
            schedule_block = f"""
schedules:
  - cron: '{cron_schedule}'
    displayName: Scheduled migration
    branches:
      include:
        - main
    always: true
"""

        yaml = f"""trigger:
  - none
{schedule_block}
pool:
  vmImage: 'ubuntu-latest'

variables:
  PBIRS_SERVER: '{server_url}'
  pythonVersion: '3.12'

stages:
  - stage: Migration
    displayName: 'PBIRS Migration'
    jobs:
      - job: Migrate
        displayName: 'Run Migration Pipeline'
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '$(pythonVersion)'

          - script: |
              python migrate.py \\
                --server $(PBIRS_SERVER) \\
                --phase all \\
                --output $(Build.ArtifactStagingDirectory)/migration
            displayName: 'Run migration'
            env:
              PBI_CLIENT_ID: $(PBI_CLIENT_ID)
              PBI_CLIENT_SECRET: $(PBI_CLIENT_SECRET)
              PBI_TENANT_ID: $(PBI_TENANT_ID)

          - task: PublishBuildArtifacts@1
            inputs:
              PathtoPublish: '$(Build.ArtifactStagingDirectory)/migration'
              ArtifactName: 'migration-artifacts'
            condition: always()
"""
        logger.info("Generated Azure DevOps pipeline")
        return yaml

    def save(
        self,
        output_dir: str,
        template_type: str = "github",
        **kwargs: str,
    ) -> Path:
        """Generate and save a pipeline template.

        Args:
            output_dir: output directory.
            template_type: "github" or "azdo".
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        if template_type == "github":
            content = self.generate_github_actions(
                server_url=kwargs.get("server_url", "https://pbirs.local/reports"),
                cron_schedule=kwargs.get("cron_schedule", ""),
            )
            path = out / ".github" / "workflows" / "migration.yml"
        else:
            content = self.generate_azure_devops(
                server_url=kwargs.get("server_url", "https://pbirs.local/reports"),
                cron_schedule=kwargs.get("cron_schedule", ""),
            )
            path = out / "azure-pipelines.yml"

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Pipeline template saved to %s", path)
        return path
