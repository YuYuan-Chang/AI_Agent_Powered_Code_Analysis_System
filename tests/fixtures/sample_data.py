"""
Sample data loader for testing CodexGraph.
Creates some example code structure data in Neo4j for testing purposes.
"""

from .graphdb.neo4j_connector import Neo4jConnector

def load_sample_data():
    """Load sample code structure data into Neo4j for testing."""
    
    connector = Neo4jConnector()
    
    # Clear existing data (use with caution!)
    print("Clearing existing data...")
    connector.execute_write_query("MATCH (n) DETACH DELETE n")
    
    # Create sample modules
    print("Creating sample modules...")
    modules_query = """
    CREATE 
        (utils:MODULE {name: "utils", file_path: "/app/utils/__init__.py"}),
        (auth:MODULE {name: "auth", file_path: "/app/auth/__init__.py"}),
        (api:MODULE {name: "api", file_path: "/app/api/__init__.py"})
    """
    connector.execute_write_query(modules_query)
    
    # Create sample classes
    print("Creating sample classes...")
    classes_query = """
    MATCH (utils:MODULE {name: "utils"}), (auth:MODULE {name: "auth"})
    CREATE 
        (base:CLASS {name: "BaseModel", file_path: "/app/utils/models.py", signature: "class BaseModel:"}),
        (user:CLASS {name: "User", file_path: "/app/auth/models.py", signature: "class User(BaseModel):"}),
        (session:CLASS {name: "SecureSession", file_path: "/app/auth/session.py", signature: "class SecureSession(BaseModel):"}),
        (validator:CLASS {name: "Validator", file_path: "/app/utils/validation.py", signature: "class Validator:"})
    """
    connector.execute_write_query(classes_query)
    
    # Create relationships
    print("Creating relationships...")
    relationships_query = """
    MATCH (utils:MODULE {name: "utils"}), (auth:MODULE {name: "auth"})
    MATCH (base:CLASS {name: "BaseModel"}), (user:CLASS {name: "User"}), 
          (session:CLASS {name: "SecureSession"}), (validator:CLASS {name: "Validator"})
    CREATE
        (utils)-[:CONTAINS]->(base),
        (utils)-[:CONTAINS]->(validator),
        (auth)-[:CONTAINS]->(user),
        (auth)-[:CONTAINS]->(session),
        (user)-[:INHERITS]->(base),
        (session)-[:INHERITS]->(base)
    """
    connector.execute_write_query(relationships_query)
    
    # Create sample methods
    print("Creating sample methods...")
    methods_query = """
    MATCH (user:CLASS {name: "User"}), (session:CLASS {name: "SecureSession"}), (validator:CLASS {name: "Validator"})
    CREATE
        (validate_method:METHOD {name: "validate", file_path: "/app/auth/models.py", signature: "def validate(self):", class: "User"}),
        (save_method:METHOD {name: "save", file_path: "/app/auth/models.py", signature: "def save(self):", class: "User"}),
        (connect_method:METHOD {name: "connect", file_path: "/app/auth/session.py", signature: "def connect(self):", class: "SecureSession"}),
        (validate_input:METHOD {name: "validate_input", file_path: "/app/utils/validation.py", signature: "def validate_input(self, data):", class: "Validator"})
    """
    connector.execute_write_query(methods_query)
    
    # Link methods to classes
    print("Linking methods to classes...")
    method_relationships_query = """
    MATCH (user:CLASS {name: "User"}), (session:CLASS {name: "SecureSession"}), (validator:CLASS {name: "Validator"})
    MATCH (validate_method:METHOD {name: "validate", class: "User"}),
          (save_method:METHOD {name: "save", class: "User"}),
          (connect_method:METHOD {name: "connect", class: "SecureSession"}),
          (validate_input:METHOD {name: "validate_input", class: "Validator"})
    CREATE
        (user)-[:HAS_METHOD]->(validate_method),
        (user)-[:HAS_METHOD]->(save_method),
        (session)-[:HAS_METHOD]->(connect_method),
        (validator)-[:HAS_METHOD]->(validate_input)
    """
    connector.execute_write_query(method_relationships_query)
    
    # Create some global variables and functions
    print("Creating functions and variables...")
    functions_query = """
    MATCH (utils:MODULE {name: "utils"}), (auth:MODULE {name: "auth"})
    CREATE
        (load_config:FUNCTION {name: "load_config", file_path: "/app/utils/config.py", signature: "def load_config():"}),
        (encrypt_password:FUNCTION {name: "encrypt_password", file_path: "/app/auth/crypto.py", signature: "def encrypt_password(password):"}),
        (api_key:GLOBAL_VARIABLE {name: "API_KEY", file_path: "/app/utils/config.py", code: "API_KEY = os.getenv('API_KEY')"}),
        (secret:GLOBAL_VARIABLE {name: "ENV_SECRET", file_path: "/app/auth/config.py", code: "ENV_SECRET = os.getenv('SECRET_KEY')"})
    """
    connector.execute_write_query(functions_query)
    
    # Link functions to modules
    functions_relationships_query = """
    MATCH (utils:MODULE {name: "utils"}), (auth:MODULE {name: "auth"})
    MATCH (load_config:FUNCTION {name: "load_config"}),
          (encrypt_password:FUNCTION {name: "encrypt_password"}),
          (api_key:GLOBAL_VARIABLE {name: "API_KEY"}),
          (secret:GLOBAL_VARIABLE {name: "ENV_SECRET"})
    CREATE
        (utils)-[:CONTAINS]->(load_config),
        (utils)-[:CONTAINS]->(api_key),
        (auth)-[:CONTAINS]->(encrypt_password),
        (auth)-[:CONTAINS]->(secret)
    """
    connector.execute_write_query(functions_relationships_query)
    
    # Create constraints and indexes
    print("Creating constraints and indexes...")
    connector.create_constraints_and_indexes()
    
    print("Sample data loaded successfully!")
    print("\nNow you can try queries like:")
    print("- 'Find all classes that inherit from BaseModel'")
    print("- 'What methods does the User class have?'")
    print("- 'List all modules'")
    print("- 'Find classes in the auth module'")
    print("- 'What is the SecureSession class?'")
    
    connector.close()

if __name__ == "__main__":
    load_sample_data()