"""Load the platform graph from NetworkX into Neo4j.

NetworkX is the source of truth. Every run wipes Neo4j and reloads it,
so the two copies never drift apart.
"""
import os

from neo4j import GraphDatabase

URI = "neo4j://127.0.0.1:7687"
SIMPLE = (str, int, float, bool)


class Neo4jLoader:
    def __init__(self, uri=URI, auth=None):
        self.uri = uri
        self.auth = auth or ("neo4j", os.environ["NEO4J_PASSWORD"])
        self.driver = None

    def __enter__(self):
        self.driver = GraphDatabase.driver(self.uri, auth=self.auth)
        self.driver.verify_connectivity()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.driver.close()

    @staticmethod
    def clean(attrs):
        """Neo4j only accepts simple values or lists of them. Convert the rest to text."""
        out = {}
        for key, value in attrs.items():
            if value is None or isinstance(value, SIMPLE):
                out[key] = value
            elif isinstance(value, (list, tuple)) and all(isinstance(v, SIMPLE) for v in value):
                out[key] = list(value)
            else:
                out[key] = str(value)
        if "name" in out:  # "name" is reserved for the node ID
            out["label"] = out.pop("name")
        return out

    def load(self, G):
        if not G.is_directed():
            print("Warning: graph is undirected, so link directions in Neo4j are arbitrary.")

        # 1. Wipe everything
        self.driver.execute_query("MATCH (n) DETACH DELETE n")

        # 2. Rule: no two assets can share a name
        self.driver.execute_query(
            "CREATE CONSTRAINT asset_name IF NOT EXISTS "
            "FOR (a:Asset) REQUIRE a.name IS UNIQUE"
        )

        # 3. Nodes
        for node, attrs in G.nodes(data=True):
            self.driver.execute_query(
                "CREATE (n:Asset {name: $name}) SET n += $props",
                name=str(node), props=self.clean(attrs),
            )

        # 4. Links
        for a, b, attrs in G.edges(data=True):
            self.driver.execute_query(
                "MATCH (x:Asset {name: $a}), (y:Asset {name: $b}) "
                "CREATE (x)-[r:LINK]->(y) SET r += $props",
                a=str(a), b=str(b), props=self.clean(attrs),
            )

    def compare_counts(self, G):
        records, _, _ = self.driver.execute_query(
            "MATCH (n) OPTIONAL MATCH (n)-[r]->() "
            "RETURN count(DISTINCT n) AS nodes, count(r) AS links"
        )
        print(f"NetworkX: {G.number_of_nodes()} nodes, {G.number_of_edges()} links")
        print(f"Neo4j:    {records[0]['nodes']} nodes, {records[0]['links']} links")
