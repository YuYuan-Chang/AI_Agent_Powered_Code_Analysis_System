"""
Neo4j connector with session management and helper functions.
Provides connection management and utility functions for interacting with Neo4j.
"""

import logging
from typing import Optional, List, Dict, Any, Union
from contextlib import contextmanager
from neo4j import GraphDatabase, Driver, Session, Record
from ..config import config


class Neo4jConnector:
    """
    Neo4j database connector that manages connections and provides helper functions.
    """
    
    def __init__(self):
        """Initialize the Neo4j connector with configuration."""
        self.driver: Optional[Driver] = None
        self.logger = logging.getLogger(__name__)
        self._connect()
    
    def _connect(self) -> None:
        """Establish connection to Neo4j database."""
        try:
            self.driver = GraphDatabase.driver(
                config.neo4j.uri,
                auth=(config.neo4j.username, config.neo4j.password)
            )
            
            # Test the connection
            with self.driver.session(database=config.neo4j.database) as session:
                session.run("RETURN 1")
            
            self.logger.info(f"Successfully connected to Neo4j at {config.neo4j.uri}")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Neo4j: {str(e)}")
            raise Exception(f"Neo4j connection failed: {str(e)}")
    
    @contextmanager
    def get_session(self):
        """
        Context manager for Neo4j sessions.
        
        Yields:
            Neo4j session object
        """
        if not self.driver:
            raise Exception("Neo4j driver not initialized")
        
        session = self.driver.session(database=config.neo4j.database)
        try:
            yield session
        finally:
            session.close()
    
    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Record]:
        """
        Execute a Cypher query and return results.
        
        Args:
            query: Cypher query string
            parameters: Optional query parameters
            
        Returns:
            List of Neo4j Record objects
            
        Raises:
            Exception: If query execution fails
        """
        try:
            self.logger.info(f"Executing query: {query}")
            if parameters:
                self.logger.debug(f"Query parameters: {parameters}")
            
            with self.get_session() as session:
                result = session.run(query, parameters or {})
                records = list(result)
                
            self.logger.info(f"Query returned {len(records)} records")
            return records
            
        except Exception as e:
            self.logger.error(f"Query execution failed: {str(e)}")
            raise Exception(f"Failed to execute query: {str(e)}")
    
    def execute_write_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute a write query (CREATE, MERGE, DELETE, etc.).
        
        Args:
            query: Cypher write query string
            parameters: Optional query parameters
            
        Returns:
            Query result summary
        """
        try:
            self.logger.info(f"Executing write query: {query}")
            
            with self.get_session() as session:
                result = session.run(query, parameters or {})
                summary = result.consume()
                
            self.logger.info(f"Write query completed: {summary.counters}")
            return summary
            
        except Exception as e:
            self.logger.error(f"Write query execution failed: {str(e)}")
            raise Exception(f"Failed to execute write query: {str(e)}")
    
    def test_connection(self) -> bool:
        """
        Test the Neo4j connection.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            with self.get_session() as session:
                result = session.run("RETURN 1 AS test")
                record = result.single()
                return record["test"] == 1
        except Exception as e:
            self.logger.error(f"Connection test failed: {str(e)}")
            return False
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get information about the Neo4j database.
        
        Returns:
            Dictionary containing database information
        """
        try:
            info = {}
            
            with self.get_session() as session:
                # Get node count by label
                result = session.run("CALL db.labels() YIELD label RETURN label")
                labels = [record["label"] for record in result]
                
                info["labels"] = labels
                info["node_counts"] = {}
                
                for label in labels:
                    count_result = session.run(f"MATCH (n:{label}) RETURN count(n) AS count")
                    count = count_result.single()["count"]
                    info["node_counts"][label] = count
                
                # Get relationship types
                result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
                rel_types = [record["relationshipType"] for record in result]
                info["relationship_types"] = rel_types
                
                # Get relationship counts
                info["relationship_counts"] = {}
                for rel_type in rel_types:
                    count_result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS count")
                    count = count_result.single()["count"]
                    info["relationship_counts"][rel_type] = count
            
            return info
            
        except Exception as e:
            self.logger.error(f"Failed to get database info: {str(e)}")
            return {}
    
    def create_constraints_and_indexes(self) -> None:
        """Create recommended constraints and indexes for the code property graph."""
        try:
            constraints_and_indexes = [
                # Unique constraints for primary identifiers
                "CREATE CONSTRAINT module_name_unique IF NOT EXISTS FOR (m:MODULE) REQUIRE m.name IS UNIQUE",
                "CREATE CONSTRAINT class_name_path_unique IF NOT EXISTS FOR (c:CLASS) REQUIRE (c.name, c.file_path) IS UNIQUE", 
                "CREATE CONSTRAINT function_name_path_unique IF NOT EXISTS FOR (f:FUNCTION) REQUIRE (f.name, f.file_path) IS UNIQUE",
                "CREATE CONSTRAINT method_name_class_unique IF NOT EXISTS FOR (m:METHOD) REQUIRE (m.name, m.class) IS UNIQUE",
                
                # Indexes for frequently queried properties
                "CREATE INDEX module_file_path_index IF NOT EXISTS FOR (m:MODULE) ON (m.file_path)",
                "CREATE INDEX class_name_index IF NOT EXISTS FOR (c:CLASS) ON (c.name)",
                "CREATE INDEX function_name_index IF NOT EXISTS FOR (f:FUNCTION) ON (f.name)",
                "CREATE INDEX method_name_index IF NOT EXISTS FOR (m:METHOD) ON (m.name)",
                "CREATE INDEX global_variable_name_index IF NOT EXISTS FOR (gv:GLOBAL_VARIABLE) ON (gv.name)",
                "CREATE INDEX field_name_index IF NOT EXISTS FOR (f:FIELD) ON (f.name)"
            ]
            
            for statement in constraints_and_indexes:
                try:
                    self.execute_write_query(statement)
                    self.logger.info(f"Created constraint/index: {statement}")
                except Exception as e:
                    # Constraint/index might already exist
                    self.logger.debug(f"Constraint/index creation skipped: {str(e)}")
            
        except Exception as e:
            self.logger.error(f"Failed to create constraints and indexes: {str(e)}")
    
    def clear_database(self) -> None:
        """
        Clear all nodes and relationships from the database.
        Use with caution!
        """
        try:
            self.logger.warning("Clearing entire database!")
            self.execute_write_query("MATCH (n) DETACH DELETE n")
            self.logger.info("Database cleared successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to clear database: {str(e)}")
            raise
    
    def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self.driver:
            self.driver.close()
            self.logger.info("Neo4j connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()