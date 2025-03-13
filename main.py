from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
from urllib.parse import urlparse
import re

app = FastAPI()

# Global variable to store the project path
project_path = ""


class RepoDetails(BaseModel):
    repo_url: str
    clone_dir: str
    new_name: str  # Allow user to specify new project name


class ModuleToRemove(BaseModel):
    module_name: str  # Allow user to specify the Angular module to remove


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
    """Removes the specified Angular module and its dependencies from the project."""
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
            flags=re.IGNORECASE,
        )

        # Remove the module route block
        content = re.sub(
            rf"\s*{{\s*path:\s*'{module_name}',\s*loadChildren:\s*\(\)\s*=>\s*[^}}]+}},?",
            "",
            content,
            flags=re.IGNORECASE,
        )

        # Remove any other references to the module
        content = re.sub(
            rf"['\"]\.\/{module_name}\/[^'\"]+['\"]", "", content, flags=re.IGNORECASE
        )

        with open(app_routing_module_path, "w") as file:
            file.write(content)

    # Remove references to the module in all other .ts files
    for root, _, files in os.walk(project_path):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            if file_path.endswith(".ts"):
                with open(file_path, "r") as file:
                    content = file.read()

                # Remove the module import statement
                content = re.sub(
                    rf"import\s+{{[^}}]+}}\s+from\s+['\"]\.\/{module_name}\/[^'\"]+['\"];",
                    "",
                    content,
                    flags=re.IGNORECASE,
                )

                # Remove the module from NgModule imports
                content = re.sub(
                    rf"{module_name}Module,?", "", content, flags=re.IGNORECASE
                )

                # Remove any other references to the module
                content = re.sub(
                    rf"['\"]\.\/{module_name}\/[^'\"]+['\"]",
                    "",
                    content,
                    flags=re.IGNORECASE,
                )

                # Remove the module route block
                content = re.sub(
                    rf"\s*{{\s*path:\s*'{module_name}',\s*loadChildren:\s*\(\)\s*=>\s*[^}}]+}},?",
                    "",
                    content,
                    flags=re.IGNORECASE,
                )

                with open(file_path, "w") as file:
                    file.write(content)


@app.post("/clone-repo/")
async def clone_repo(repo_details: RepoDetails):
    global project_path
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

        # Set the global project path
        project_path = renamed_path

        # Get all available Angular modules
        angular_modules = get_angular_modules(renamed_path)

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


@app.post("/remove-module/")
async def remove_module(module_details: ModuleToRemove):
    global project_path
    try:
        # Get all available Angular modules
        angular_modules = get_angular_modules(project_path)

        # Remove the specified Angular module and its dependencies
        if module_details.module_name in angular_modules:
            remove_angular_module(project_path, module_details.module_name)
            angular_modules.remove(module_details.module_name)
            return {
                "message": f"Module '{module_details.module_name}' removed successfully",
                "remaining_modules": angular_modules,
            }
        else:
            raise HTTPException(status_code=404, detail="Module not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# To run the FastAPI app, use the command: uvicorn main:app --reload
