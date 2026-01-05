import os
import pytest
from unittest.mock import MagicMock, patch
from pytron.apputils.codegen import CodegenMixin

class MockApp(CodegenMixin):
    def __init__(self):
        self.logger = MagicMock()
        self._pydantic_models = {}
        self._exposed_ts_defs = {}
        
        # Mock _python_type_to_ts if needed, but we want to test it
        # So we leave it as is.

@pytest.fixture
def app():
    return MockApp()

def test_python_type_to_ts_basics(app):
    assert app._python_type_to_ts(str) == "string"
    assert app._python_type_to_ts(int) == "number"
    assert app._python_type_to_ts(bool) == "boolean"
    assert app._python_type_to_ts(type(None)) == "void"
    assert app._python_type_to_ts(list) == "any[]"
    assert app._python_type_to_ts(dict) == "Record<string, any>"

def test_python_type_to_ts_generics(app):
    from typing import List, Dict, Union, Optional
    
    assert app._python_type_to_ts(List[str]) == "string[]"
    assert app._python_type_to_ts(Dict[str, int]) == "Record<string, number>"
    assert app._python_type_to_ts(Union[str, int]) == "string | number"
    assert app._python_type_to_ts(Optional[str]) == "string | null"

def test_generate_types(app, tmp_path):
    output_file = tmp_path / "pytron.d.ts"
    
    # Mock Webview methods to avoid import issues or side effects
    with patch("pytron.apputils.codegen.Webview") as mock_webview:
        # Add some dummy exposed functions
        app._exposed_ts_defs["my_func"] = "    my_func(a: string): Promise<void>;"
        
        app.generate_types(str(output_file))
        
    assert output_file.exists()
    content = output_file.read_text()
    
    assert "declare module 'pytron-client'" in content
    assert "interface PytronClient" in content
    assert "my_func(a: string): Promise<void>;" in content
    # Since Webview is mocked, it falls back to generic signature
    # MagicMock has (*args, **kwargs) signature
    assert "minimize(args: any, kwargs: any): Promise<any>;" in content

def test_pydantic_model_generation(app):
    try:
        from pydantic import BaseModel
    except ImportError:
        pytest.skip("Pydantic not installed")
        
    class User(BaseModel):
        name: str
        age: int
        
    # Trigger type conversion to register the model
    ts_type = app._python_type_to_ts(User)
    assert ts_type == "User"
    assert "User" in app._pydantic_models
    
    # Generate interface
    interface = app._generate_pydantic_interface("User", User)
    assert "export interface User {" in interface
    assert "name: string;" in interface
    assert "age: number;" in interface
