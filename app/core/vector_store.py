# app/core/vector_store.py

import os
import logging
import numpy as np
import json
import pickle
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Import Embeddings class directly
from app.core.embeddings import Embeddings

logger = logging.getLogger(__name__)

def debug_store(self):
    """Print debug information about the vector store."""
    print("\n===== VECTOR STORE DEBUG INFO =====")
    print(f"Documents in store: {len(self.documents)}")
    
    for i, doc in enumerate(self.documents):
        print(f"\nDocument {i+1}:")
        print(f"  Filename: {doc.get('filename', 'Unknown')}")
        print(f"  Type: {doc.get('metadata', {}).get('type', 'Unknown')}")
        print(f"  Content length: {len(doc.get('content', ''))}")
        print(f"  Content snippet: {doc.get('content', '')[:100]}...")
        
        if len(self.document_embeddings) > i:
            embedding = self.document_embeddings[i]
            print(f"  Embedding shape: {embedding.shape}")
            print(f"  Embedding sample: {embedding[:5]}...")
        else:
            print("  No embedding found for this document")
    
    print("\n===== END DEBUG INFO =====")

class VectorStore:
    """Class for managing vector embeddings of documents."""
    
    def __init__(self, store_dir: Optional[str] = None, cache_dir: Optional[str] = None):
        """
        Initialize the vector store.
        
        Args:
            store_dir: Directory to store embeddings
            cache_dir: Directory to cache document data
        """
        self.documents = []
        self.embeddings_model = Embeddings()  # Use ArabERT by default
        self.document_embeddings = []
        
        # Set up directories
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.store_dir = store_dir or os.path.join(base_dir, "data", "embeddings")
        self.cache_dir = cache_dir or os.path.join(base_dir, "data", "cache")
        
        # Create directories if they don't exist
        os.makedirs(self.store_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Cache file for documents
        self.documents_cache_file = os.path.join(self.cache_dir, "documents.pkl")
        self.embeddings_cache_file = os.path.join(self.cache_dir, "embeddings.pkl")
        
        # Load cached documents and embeddings if available
        self._load_cache()
        
        logger.info(f"Initialized vector store with {len(self.documents)} documents")
        
    def query_with_debug(self, query_text: str, top_k: int = 5) -> list:
        """
        Query the vector store with debug information.
        """
        print(f"\n===== QUERY DEBUG =====")
        print(f"Query: {query_text}")
        print(f"Documents in store: {len(self.documents)}")
        
        # Call the original query method
        results = self.query(query_text, top_k)
        
        print(f"Results found: {len(results)}")
        for i, result in enumerate(results):
            print(f"Result {i+1}:")
            print(f"  Filename: {result.get('filename', 'Unknown')}")
            print(f"  Score: {result.get('score', 0)}")
            print(f"  Content snippet: {result.get('content', '')[:100]}...")
        
        print("===== END QUERY DEBUG =====\n")
        return results

    def add_document(self, document: Dict[str, Any]) -> None:
        """
        Add a document to the vector store.
        
        Args:
            document: Document data including content and metadata
        """
        try:
            # Check if document already exists (by filename)
            filename = document.get("filename", "")
            if any(doc.get("filename", "") == filename for doc in self.documents):
                logger.info(f"Document already exists: {filename}")
                return
            
            # Add document
            self.documents.append(document)
            
            # Generate embedding for the document content
            content = document.get("content", "")
            if content:
                embedding = self.embeddings_model.get_embeddings(content)
                self.document_embeddings.append(embedding[0])  # Take first since it returns a batch
            else:
                # Empty document, use zero vector
                self.document_embeddings.append(np.zeros(768))
            
            logger.info(f"Added document: {document.get('filename', 'unknown')}")
            
            # Save updated data
            self._save_cache()
            
        except Exception as e:
            logger.error(f"Error adding document: {str(e)}")
    
    def clear(self) -> None:
        """Clear all documents from the vector store."""
        self.documents = []
        self.document_embeddings = []
        
        # Clear cache files
        try:
            if os.path.exists(self.documents_cache_file):
                os.remove(self.documents_cache_file)
            
            if os.path.exists(self.embeddings_cache_file):
                os.remove(self.embeddings_cache_file)
            
            # Also clear any other cache files
            for filename in os.listdir(self.cache_dir):
                if filename.endswith(('.pkl', '.embeddings', '.cache')):
                    os.remove(os.path.join(self.cache_dir, filename))
        except Exception as e:
            logger.error(f"Error clearing cache files: {str(e)}")
        
        logger.info("Cleared vector store")
    
    def save(self) -> None:
        """Save the vector store to disk."""
        self._save_cache()
        logger.info(f"Saved vector store with {len(self.documents)} documents")
    
    def get_documents(self) -> List[Dict[str, Any]]:
        """Get all documents in the vector store."""
        return self.documents
    
    def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Query the vector store for relevant documents with improved reliability.
        
        Args:
            query_text: Query text
            top_k: Number of top results to return
            
        Returns:
            List of relevant documents with scores
        """
        try:
            if not self.documents:
                logger.info("No documents in vector store")
                return []
            
            # Generate embedding for the query
            query_embedding = self.embeddings_model.get_embeddings(query_text)[0]
            
            # Calculate similarity scores
            scores = []
            for i, doc_embedding in enumerate(self.document_embeddings):
                # Use a more reliable similarity calculation
                similarity = float(self.embeddings_model.similarity(query_embedding, doc_embedding))
                
                # Add document index and similarity score
                scores.append((i, similarity))
            
            # Sort by similarity score (descending)
            scores.sort(key=lambda x: x[1], reverse=True)
            
            # Get top-k results
            results = []
            for i, score in scores[:top_k]:
                # Create a copy to avoid modifying the original document
                if i < len(self.documents):
                    doc = self.documents[i].copy()
                    doc["score"] = float(score)  # Convert numpy float to Python float
                    
                    # Ensure the document has content
                    if "content" not in doc or not doc["content"]:
                        logger.warning(f"Document {i} has no content")
                        continue
                        
                    results.append(doc)
            
            # Log the results for debugging
            logger.info(f"Query: '{query_text}' returned {len(results)} results")
            for i, doc in enumerate(results):
                logger.info(f"Result {i+1}: {doc.get('filename', 'Unknown')} (score: {doc.get('score', 0)})")
            
            return results
            
        except Exception as e:
            logger.error(f"Error querying vector store: {str(e)}")
            return []
    
    def _save_cache(self) -> None:
        """Save documents and embeddings to cache files."""
        try:
            # Save documents
            with open(self.documents_cache_file, "wb") as f:
                pickle.dump(self.documents, f)
            
            # Save embeddings
            with open(self.embeddings_cache_file, "wb") as f:
                pickle.dump(self.document_embeddings, f)
                
        except Exception as e:
            logger.error(f"Error saving cache: {str(e)}")
    
    def _load_cache(self) -> None:
        """Load documents and embeddings from cache files."""
        try:
            # Load documents
            if os.path.exists(self.documents_cache_file):
                with open(self.documents_cache_file, "rb") as f:
                    self.documents = pickle.load(f)
            
            # Load embeddings
            if os.path.exists(self.embeddings_cache_file):
                with open(self.embeddings_cache_file, "rb") as f:
                    self.document_embeddings = pickle.load(f)
            
            # Ensure lengths match
            if len(self.documents) != len(self.document_embeddings):
                logger.warning("Mismatch between documents and embeddings counts, resetting")
                self.documents = []
                self.document_embeddings = []
                
        except Exception as e:
            logger.error(f"Error loading cache: {str(e)}")
            # Reset in case of error
            self.documents = []
            self.document_embeddings = []
    
    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by its ID."""
        for doc in self.documents:
            if doc.get("id") == doc_id:
                return doc
        return None
    
    def get_document_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """Get a document by its filename."""
        for doc in self.documents:
            if doc.get("filename") == filename:
                return doc
        return None