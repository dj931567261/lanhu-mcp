"""Basic tests for Lanhu MCP Server"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_python_version():
    """Test that Python version is 3.10 or higher"""
    assert sys.version_info >= (3, 10), "Python 3.10+ is required"


def test_imports():
    """Test that required packages can be imported"""
    try:
        import fastmcp
        import httpx
        import bs4
        import playwright
        import lxml
        assert True
    except ImportError as e:
        assert False, f"Import failed: {e}"


def test_project_structure():
    """Test that key project files exist"""
    assert (project_root / "lanhu_mcp_server.py").exists()
    assert (project_root / "requirements.txt").exists()
    assert (project_root / "README.md").exists()
    assert (project_root / "pyproject.toml").exists()


def test_data_directory_creation():
    """Test that data directories can be created"""
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)
    assert data_dir.exists()
    
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    assert logs_dir.exists()

