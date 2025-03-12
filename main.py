from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
from urllib.parse import urlparse
import re

app = FastAPI()


class RepoDetails(BaseModel):
    repo_url: str
    clone_dir: str
    new_name: str  # Allow user to specify new project name
    module_to_remove: str  # Allow user to specify the Angular module to remove


def get_project_name(repo_url: str) -> str:
    """Extracts the project name from the Git repository URL."""
    parsed_url = urlparse(repo_url)
    project_name = os.path.basename(parsed_url.path)
    if project_name.endswith(".git"):
        project_name = project_name[:-4]
    return project_name


def get_angular_modules(project_path: str):
    """Returns Angular modules inside 'src/app/'."""
    angular_modules = []

    # Path for Angular modules
    angular_module_path = os.path.join(project_path, "src", "app")

    if os.path.exists(angular_module_path):
        # List Angular modules inside 'src/app/'
        angular_modules = [
            d
            for d in os.listdir(angular_module_path)
            if os.path.isdir(os.path.join(angular_module_path, d))
        ]

    return angular_modules


def remove_angular_module(project_path: str, module_name: str):
    """Removes the specified Angular module and its dependencies from app-routing.module.ts."""
    angular_module_path = os.path.join(project_path, "src", "app", module_name)

    # Remove the module directory
    if os.path.exists(angular_module_path):
        subprocess.run(["rm", "-rf", angular_module_path])

    # Update app-routing.module.ts
    app_routing_module_path = os.path.join(
        project_path, "src", "app", "app-routing.module.ts"
    )
    if os.path.exists(app_routing_module_path):
        with open(app_routing_module_path, "r") as file:
            content = file.read()

        # Remove the module import statement
        content = re.sub(
            rf"import\s+{{[^}}]+}}\s+from\s+['\"]\.\/{module_name}\/[^'\"]+['\"];",
            "",
            content,
        )

        # Remove the module route
        content = re.sub(
            rf"\s*{{\s*path:\s*'{module_name}',\s*loadChildren:\s*\(\)\s*=>\s*import\(['\"]\.\/{module_name}\/[^'\"]+['\"]\)\.then\(m\s*=>\s*m\.[^}}]+}},",
            "",
            content,
        )

        with open(app_routing_module_path, "w") as file:
            file.write(content)


@app.post("/clone-repo/")
async def clone_repo(repo_details: RepoDetails):
    try:
        # Ensure the base clone directory exists
        if not os.path.exists(repo_details.clone_dir):
            os.makedirs(repo_details.clone_dir)

        # Get original project name
        original_project_name = get_project_name(repo_details.repo_url)

        # Define paths
        original_path = os.path.join(repo_details.clone_dir, original_project_name)
        renamed_path = os.path.join(repo_details.clone_dir, repo_details.new_name)

        # Clone the repository
        result = subprocess.run(
            ["git", "clone", repo_details.repo_url, original_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Check for cloning errors
        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=result.stderr.strip())

        # Rename the project directory
        if os.path.exists(original_path):
            os.rename(original_path, renamed_path)
        else:
            raise HTTPException(
                status_code=400,
                detail="Cloning successful, but project folder not found.",
            )

        # Get all available Angular modules
        angular_modules = get_angular_modules(renamed_path)

        # Remove the specified Angular module and its dependencies
        if repo_details.module_to_remove in angular_modules:
            remove_angular_module(renamed_path, repo_details.module_to_remove)
            angular_modules.remove(repo_details.module_to_remove)

        return {
            "message": "Repository cloned and renamed successfully",
            "original_project_name": original_project_name,
            "new_project_name": repo_details.new_name,
            "clone_location": renamed_path,
            "angular_modules": angular_modules,
            "output": (result.stdout + result.stderr).strip() or "No output from git.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# To run the FastAPI app, use the command: uvicorn main:app --reload
