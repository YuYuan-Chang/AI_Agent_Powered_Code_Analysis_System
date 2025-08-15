"""
Iterative pipeline for multi-step LLM → Cypher → result → sufficiency check.
Implements the core search logic with iterative refinement using OpenAI Structured Outputs.
"""

import logging
from typing import Dict, List, Optional
import openai
import time

from ..agents.primary_agent import PrimaryAgent
from ..agents.translator_agent import TranslatorAgent
from ..agents.summary_agent import SummaryAgent
from ..agents.rag_agent import RAGAgent
from ..graphdb.neo4j_connector import Neo4jConnector
from ..graphdb.query_executor import QueryExecutor, QueryResult
from ..config import config
from ..utils.prompts import SUFFICIENCY_ANALYSIS_PROMPT, RESULT_FORMATTING_PROMPT
from ..utils.openai_logger import openai_logger
from ..models.analysis_models import SufficiencyAnalysis
from ..models.search_models import SearchIteration, SearchResult



class IterativePipeline:
    """
    Multi-step pipeline that iteratively refines queries until sufficient results are found.
    """
    
    def __init__(self, 
                 connector: Optional[Neo4jConnector] = None,
                 primary_agent: Optional[PrimaryAgent] = None,
                 translator_agent: Optional[TranslatorAgent] = None,
                 summary_agent: Optional[SummaryAgent] = None,
                 query_executor: Optional[QueryExecutor] = None,
                 rag_agent: Optional[RAGAgent] = None,
                 base_path: Optional[str] = None):
        """
        Initialize the iterative pipeline.
        
        Args:
            connector: Neo4j connector instance
            primary_agent: Primary agent for understanding queries
            translator_agent: Translator agent for generating Cypher
            summary_agent: Summary agent for generating natural language summaries
            query_executor: Query executor for running Cypher queries
            rag_agent: RAG agent for document-based search
            base_path: Base path for resolving source code file paths
        """
        self.connector = connector or Neo4jConnector()
        self.primary_agent = primary_agent or PrimaryAgent()
        self.translator_agent = translator_agent or TranslatorAgent()
        self.summary_agent = summary_agent or SummaryAgent()
        self.query_executor = query_executor or QueryExecutor(self.connector, base_path=base_path)
        self.rag_agent = rag_agent or RAGAgent()
        
        self.openai_client = openai.OpenAI(api_key=config.openai.api_key)
        self.logger = logging.getLogger(__name__)
        
        self.max_iterations = config.pipeline.max_iterations
        self.sufficiency_threshold = config.pipeline.sufficiency_threshold
        
        # Log RAG availability
        if self.rag_agent.is_available():
            self.logger.info("RAG agent is available and ready")
        else:
            self.logger.warning("RAG agent is not available - only graph-based search will be used")
    
    def search(self, user_query: str) -> SearchResult:
        """
        Execute the iterative search pipeline.
        
        Args:
            user_query: Natural language query from the user
            
        Returns:
            SearchResult object containing the complete search process and results
        """
        import time
        start_time = time.time()
        
        self.logger.info(f"Starting iterative search for query: {user_query}")
        
        try:
            iterations = []
            all_records = []  # Collect all records from all iterations
            current_query = user_query
            
            for iteration_num in range(1, self.max_iterations + 1):
                self.logger.info(f"Starting iteration {iteration_num}")
                
                # Step 1: Primary Agent - understand the query and generate multiple intents
                try:
                    primary_response = self.primary_agent.understand_query(current_query)
                    query_intents = primary_response.query_intents
                    self.logger.info(f"Primary agent generated {len(query_intents)} query intent(s)")
                    for i, intent in enumerate(query_intents):
                        self.logger.info(f"  Intent {i+1} (priority {intent.priority}): {intent.nl_intent}")
                except Exception as e:
                    return self._create_error_result(user_query, f"Primary agent failed: {str(e)}", iterations)
                
                # Step 2: Process each intent through BOTH graph and RAG pipelines
                all_intent_results = []
                combined_cypher_queries = []
                
                for intent_idx, query_intent in enumerate(query_intents):
                    self.logger.info(f"Processing intent {intent_idx + 1}/{len(query_intents)}: {query_intent.nl_intent}")
                    
                    intent_result = {
                        'intent': query_intent,
                        'graph_result': None,
                        'rag_result': None,
                        'combined_summary': None,
                        'success': False
                    }
                    
                    # 2.1: Execute on Graph Database
                    try:
                        translator_response = self.translator_agent.translate_to_cypher(query_intent.nl_intent)
                        cypher_query = translator_response.cypher_query
                        combined_cypher_queries.append(f"-- Intent {intent_idx + 1}: {query_intent.nl_intent}\n{cypher_query}")
                        
                        graph_result = self.query_executor.execute(cypher_query)
                        intent_result['graph_result'] = {
                            'cypher': cypher_query,
                            'result': graph_result,
                            'translator_response': translator_response,
                            'success': graph_result.success,
                            'records_count': len(graph_result.records)
                        }
                        
                        self.logger.info(f"Graph query for intent {intent_idx + 1}: {len(graph_result.records)} results")
                        
                    except Exception as e:
                        self.logger.error(f"Graph query failed for intent {intent_idx + 1}: {str(e)}")
                        intent_result['graph_result'] = {
                            'cypher': f"ERROR: {str(e)}",
                            'result': None,
                            'success': False,
                            'records_count': 0,
                            'error': str(e)
                        }
                    
                    # 2.2: Execute on RAG Pipeline
                    if self.rag_agent.is_available():
                        try:
                            rag_search_result = self.rag_agent.search_documents(
                                query=query_intent.nl_intent,
                                k=5
                            )
                            intent_result['rag_result'] = {
                                'search_result': rag_search_result,
                                'success': rag_search_result.success,
                                'documents_count': rag_search_result.documents_found
                            }
                            
                            self.logger.info(f"RAG search for intent {intent_idx + 1}: {rag_search_result.documents_found} documents")
                            
                        except Exception as e:
                            self.logger.error(f"RAG search failed for intent {intent_idx + 1}: {str(e)}")
                            intent_result['rag_result'] = {
                                'success': False,
                                'documents_count': 0,
                                'error': str(e)
                            }
                    else:
                        intent_result['rag_result'] = {
                            'success': False,
                            'documents_count': 0,
                            'error': 'RAG agent not available'
                        }
                    
                    # 2.3: Generate combined summary for this intent
                    intent_result['combined_summary'] = self._generate_intent_summary(
                        query_intent.nl_intent, 
                        intent_result['graph_result'], 
                        intent_result['rag_result']
                    )
                    # Do not generate a summary; concatenate raw results into a single string
                    # try:
                    #     graph_text = ""
                    #     if (
                    #         intent_result['graph_result']
                    #         and intent_result['graph_result'].get('success')
                    #         and intent_result['graph_result'].get('result')
                    #     ):
                    #         records = intent_result['graph_result']['result'].records
                    #         graph_text = json.dumps(records, ensure_ascii=False)
                    #     rag_text = ""
                    #     if (
                    #         intent_result['rag_result']
                    #         and intent_result['rag_result'].get('success')
                    #         and intent_result['rag_result'].get('documents_count', 0) > 0
                    #         and intent_result['rag_result'].get('search_result')
                    #     ):
                    #         key_files = intent_result['rag_result']['search_result'].key_files
                    #         rag_text = json.dumps(key_files, ensure_ascii=False)
                    #     intent_result['combined_summary'] = f"graph={graph_text} | rag={rag_text}"
                    # except Exception as _e:
                    #     intent_result['combined_summary'] = "graph= | rag="
                    
                    # Mark as successful if either source provided results
                    intent_result['success'] = (
                        (intent_result['graph_result']['success'] and intent_result['graph_result']['records_count'] > 0) or
                        (intent_result['rag_result']['success'] and intent_result['rag_result']['documents_count'] > 0)
                    )
                    
                    all_intent_results.append(intent_result)
                
                # Step 3: Combine results from all intents (for backward compatibility metrics)
                combined_query_result = self._combine_intent_results(all_intent_results)
                
                # Collect all records from this iteration's successful queries
                if combined_query_result.success and combined_query_result.records:
                    all_records.extend(combined_query_result.records)
                
                # For logging and iteration tracking, use the primary intent
                primary_intent = min(query_intents, key=lambda x: x.priority)
                nl_intent = primary_intent.nl_intent
                cypher_query = "\n\n".join(combined_cypher_queries)
                
                # Step 4: Merge all individual summaries into comprehensive overview
                result_summary = self._merge_all_summaries(user_query, all_intent_results)
                
                # Calculate total counts for tracking
                total_graph_records = sum(
                    intent['graph_result']['records_count'] for intent in all_intent_results
                    if intent['graph_result'] and intent['graph_result']['success']
                )
                total_rag_documents = sum(
                    intent['rag_result']['documents_count'] for intent in all_intent_results
                    if intent['rag_result'] and intent['rag_result']['success']
                )
                
                # Step 5: Perform sufficiency check on combined summary
                sufficiency_analysis = self._analyze_combined_sufficiency(
                    user_query, result_summary, all_intent_results, iteration_num
                )
                
                # Safety mechanism: If we have valid results and tried multiple iterations, 
                # consider it sufficient to prevent infinite loops
                if (combined_query_result.success and 
                    len(combined_query_result.records) > 0 and 
                    iteration_num >= 2):
                    sufficiency_analysis.sufficient = True
                    sufficiency_analysis.confidence = max(sufficiency_analysis.confidence, 0.8)
                    self.logger.info(f"Auto-marking as sufficient after {iteration_num} iterations with {len(combined_query_result.records)} results")
                
                # Additional safety mechanism: If we consistently get 0 results after multiple iterations,
                # consider it sufficient to prevent infinite loops when no relevant data exists
                elif (combined_query_result.success and 
                      len(combined_query_result.records) == 0 and 
                      iteration_num >= 3):
                    sufficiency_analysis.sufficient = True
                    sufficiency_analysis.confidence = 0.9  # High confidence that no data exists
                    sufficiency_analysis.missing_info = ''
                    sufficiency_analysis.suggested_followup = ''
                    self.logger.info(f"Auto-marking as sufficient after {iteration_num} iterations with consistent 0 results - no relevant data found")
                
                iteration = SearchIteration(
                    iteration_number=iteration_num,
                    nl_intent=nl_intent,
                    cypher_query=cypher_query,
                    result_summary=result_summary,
                    records_count=total_graph_records,
                    execution_time_ms=combined_query_result.execution_time_ms,
                    sufficient=sufficiency_analysis.sufficient,
                    confidence=sufficiency_analysis.confidence,
                    feedback=sufficiency_analysis.missing_info,
                    query_success=combined_query_result.success,
                    rag_summary="Integrated in combined summary",  # RAG is now integrated
                    rag_documents_count=total_rag_documents
                )
                
                iterations.append(iteration)
                
                # Check if results are sufficient
                if (sufficiency_analysis.sufficient and 
                    sufficiency_analysis.confidence >= self.sufficiency_threshold):
                    self.logger.info(f"Sufficient results found after {iteration_num} iterations")
                    break
                
                # Prepare for next iteration if not at max
                if iteration_num < self.max_iterations:
                    if sufficiency_analysis.suggested_followup:
                        current_query = sufficiency_analysis.suggested_followup
                    else:
                        # Use the feedback to refine the query
                        current_query = self._refine_query_for_next_iteration(
                            user_query, sufficiency_analysis.missing_info
                        )
                    
                    self.logger.info(f"Refined query for next iteration: {current_query}")
            
            # Format final results
            # print(f"\n📄 FINAL iterations:")
            # print(iterations)
            self.logger.info(f"Generating final report for query: {user_query}")
            final_answer = self._format_final_results(user_query, iterations)
            
            # all_records has been populated during iteration processing above
            
            total_time = (time.time() - start_time) * 1000
            
            search_result = SearchResult(
                original_query=user_query,
                iterations=iterations,
                final_answer=final_answer,
                success=True,
                total_execution_time_ms=total_time,
                records=all_records
            )
            
            self.logger.info(f"Search completed successfully - {len(iterations)} iterations, {len(all_records)} total records, {total_time:.1f}ms")
            
            return search_result
        
        except Exception as e:
            self.logger.error(f"Pipeline execution failed: {str(e)}")
            total_time = (time.time() - start_time) * 1000
            
            return SearchResult(
                original_query=user_query,
                iterations=iterations,
                final_answer=f"Search failed: {str(e)}",
                success=False,
                total_execution_time_ms=total_time,
                error_message=str(e),
                records=[]
            )
    
    
    
    def _combine_query_results(self, all_query_results: List[Dict]) -> QueryResult:
        """
        Combine multiple query results into a single QueryResult.
        
        Args:
            all_query_results: List of dictionaries containing query results from multiple intents
            
        Returns:
            Combined QueryResult object
        """
        combined_records = []
        combined_execution_time = 0.0
        successful_queries = 0
        error_messages = []
        
        for query_data in all_query_results:
            result = query_data['result']
            intent = query_data['intent']
            
            if result and result.success:
                # Add records without debug metadata
                for record in result.records:
                    combined_records.append(dict(record))
                
                combined_execution_time += result.execution_time_ms
                successful_queries += 1
            else:
                error_msg = f"Intent '{intent.nl_intent}': {query_data['cypher']}"
                error_messages.append(error_msg)
        
        # Create combined QueryResult
        from ..graphdb.query_executor import QueryResult
        
        combined_result = QueryResult(
            records=combined_records,
            summary={"total_intents": len(all_query_results), "successful_queries": successful_queries},
            execution_time_ms=combined_execution_time,
            success=successful_queries > 0,  # Success if at least one query succeeded
            error_message="; ".join(error_messages) if error_messages else None
        )
        
        self.logger.info(f"Combined {len(all_query_results)} query results: "
                        f"{successful_queries} successful, {len(combined_records)} total records")
        
        return combined_result
    
    def _refine_query_for_next_iteration(self, original_query: str, feedback: str) -> str:
        """
        Refine the query for the next iteration based on feedback.
        
        Args:
            original_query: The original user query
            feedback: Feedback about what's missing
            
        Returns:
            Refined query for next iteration
        """
        try:
            refinement_prompt = f"""
            Original query: "{original_query}"
            Feedback on missing information: "{feedback}"
            
            Provide a refined version of the original query that addresses the missing information.
            Make it more specific or ask for additional related information.
            Keep it as a natural language query.
            """
            
            response = self.openai_client.chat.completions.create(
                model=config.openai.model,
                messages=[{"role": "user", "content": refinement_prompt}],
                temperature=1.0,
                max_completion_tokens=None
            )
            
            refined_query = response.choices[0].message.content.strip()
            return refined_query
            
        except Exception as e:
            self.logger.error(f"Query refinement failed: {str(e)}")
            # Fallback to original query
            return original_query
    
    def _format_final_results(self, original_query: str, iterations: List[SearchIteration]) -> str:
        """
        Format the final results from all iterations into a user-friendly response.
        
        Args:
            original_query: The original user query
            iterations: List of all search iterations
            
        Returns:
            Formatted final answer
        """
        try:
            # Collect all summaries from iterations (both graph and RAG results)
            all_summaries = []
            total_records = 0
            total_rag_documents = 0
            
            for iteration in iterations:
                if iteration.query_success and iteration.result_summary:
                    all_summaries.append(f"Iteration {iteration.iteration_number}: {iteration.result_summary}")
                    total_records += iteration.records_count
                    total_rag_documents += iteration.rag_documents_count
            
            # Format summaries for final report
            if all_summaries:
                results_text = "\n\n".join(all_summaries)
                results_text += f"\n\n**Summary Statistics:**\n"
                results_text += f"- Graph Database Results: {total_records} records\n"
                results_text += f"- Document Search Results: {total_rag_documents} documents"
            else:
                results_text = "No results found across all iterations."
            
            prompt = RESULT_FORMATTING_PROMPT.format(
                original_query=original_query,
                search_results=results_text
            )
            
            # Log the final report generation API call
            start_time = time.time()
            messages = [{"role": "user", "content": prompt}]
            
            response = self.openai_client.chat.completions.create(
                model="gpt-5",
                messages=messages,
                temperature=1.0,
                max_completion_tokens=None
            )
            
            # Log the API call details
            duration_ms = (time.time() - start_time) * 1000
            openai_logger.log_api_call(
                method="chat.completions.create",
                messages=messages,
                model="gpt-5",
                temperature=1.0,
                max_tokens=None,
                response=response,
                duration_ms=duration_ms,
                agent_name="FinalReportAgent"
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            self.logger.error(f"Result formatting failed: {str(e)}")
            
            # Instead of raw data fallback, return a simple formatted summary
            if not iterations:
                return "No search iterations completed."
            
            # Create a simple markdown report as fallback
            total_records = sum(iter.records_count for iter in iterations if iter.query_success)
            fallback_report = f"""# Analysis Results

            **Query:** {original_query}

            **Summary:** Found {total_records} results across {len(iterations)} iterations.

            **Note:** Detailed system analysis report generation failed. Summary-based processing completed successfully.

            **Error:** {str(e)}
            """
            return fallback_report
    
    def _generate_intent_summary(self, intent: str, graph_result: Dict, rag_result: Dict) -> str:
        """
        Generate a combined summary for a single intent using both graph and RAG results.
        
        Args:
            intent: The natural language intent
            graph_result: Graph database query result
            rag_result: RAG search result
            
        Returns:
            Combined summary string
        """
        try:
            summary_parts = []
            
            # Add graph results
            if graph_result and graph_result['success'] and graph_result['records_count'] > 0:
                graph_summary = self.summary_agent.generate_summary(graph_result['result'], intent)
                summary_parts.append(f"**Graph Results:** {graph_summary}")
            elif graph_result and not graph_result['success']:
                summary_parts.append(f"**Graph Results:** Query failed - {graph_result.get('error', 'Unknown error')}")
            else:
                summary_parts.append("**Graph Results:** No structural data found")
            
            # Add RAG results
            if rag_result and rag_result['success'] and rag_result['documents_count'] > 0:
                search_result = rag_result['search_result']
                rag_files_info = []
                for file_info in search_result.key_files:  # Top 3 files
                    file_desc = f"{file_info['file']} ({file_info['language']}) - {file_info['content']}..."
                    rag_files_info.append(file_desc)
                
                rag_summary = f"Found {rag_result['documents_count']} relevant documents: " + "; ".join(rag_files_info)
                summary_parts.append(f"**Document Results:** {rag_summary}")
            elif rag_result and not rag_result['success']:
                summary_parts.append(f"**Document Results:** Search failed - {rag_result.get('error', 'Unknown error')}")
            else:
                summary_parts.append("**Document Results:** No relevant documents found")
            
            return " | ".join(summary_parts)
            
        except Exception as e:
            self.logger.error(f"Failed to generate intent summary: {str(e)}")
            return f"Summary generation failed for intent: {intent}"
    
    def _merge_all_summaries(self, user_query: str, all_intent_results: List[Dict]) -> str:
        """
        Merge all individual intent summaries into a comprehensive overview.
        
        Args:
            user_query: Original user query
            all_intent_results: List of intent results with summaries
            
        Returns:
            Comprehensive merged summary
        """
        try:
            # Collect successful intent summaries
            successful_summaries = []
            total_graph_results = 0
            total_rag_documents = 0
            
            for i, intent_result in enumerate(all_intent_results):
                if intent_result['success'] and intent_result['combined_summary']:
                    summary = f"**Intent {i+1} ({intent_result['intent'].nl_intent}):** {intent_result['combined_summary']}"
                    successful_summaries.append(summary)
                    
                    # Count results
                    if intent_result['graph_result'] and intent_result['graph_result']['success']:
                        total_graph_results += intent_result['graph_result']['records_count']
                    if intent_result['rag_result'] and intent_result['rag_result']['success']:
                        total_rag_documents += intent_result['rag_result']['documents_count']
            
            if not successful_summaries:
                return "No successful results found across all query intents."
            
            # Create comprehensive overview
            merged_summary = f"**Comprehensive Analysis Results**\n\n"
            merged_summary += f"**Query:** {user_query}\n\n"
            merged_summary += f"**Summary:** Found {total_graph_results} graph records and {total_rag_documents} relevant documents across {len(successful_summaries)} successful intents.\n\n"
            merged_summary += "**Detailed Findings:**\n\n"
            merged_summary += "\n\n".join(successful_summaries)
            
            return merged_summary
            
        except Exception as e:
            self.logger.error(f"Failed to merge summaries: {str(e)}")
            return f"Failed to merge results: {str(e)}"
    
    def _combine_intent_results(self, all_intent_results: List[Dict]) -> QueryResult:
        """
        Combine results from all intents for backward compatibility with existing metrics.
        
        Args:
            all_intent_results: List of intent results
            
        Returns:
            Combined QueryResult object
        """
        combined_records = []
        combined_execution_time = 0.0
        successful_queries = 0
        error_messages = []
        
        for intent_result in all_intent_results:
            graph_result = intent_result.get('graph_result')
            
            if graph_result and graph_result['success'] and graph_result['result']:
                # Add records from successful graph queries
                for record in graph_result['result'].records:
                    combined_records.append(dict(record))
                
                combined_execution_time += graph_result['result'].execution_time_ms
                successful_queries += 1
            elif graph_result and not graph_result['success']:
                error_msg = f"Intent '{intent_result['intent'].nl_intent}': {graph_result.get('error', 'Unknown error')}"
                error_messages.append(error_msg)
        
        # Create combined QueryResult
        from ..graphdb.query_executor import QueryResult
        
        combined_result = QueryResult(
            records=combined_records,
            summary={"total_intents": len(all_intent_results), "successful_queries": successful_queries},
            execution_time_ms=combined_execution_time,
            success=successful_queries > 0,
            error_message="; ".join(error_messages) if error_messages else None
        )
        
        self.logger.info(f"Combined {len(all_intent_results)} intent results: "
                        f"{successful_queries} successful, {len(combined_records)} total records")
        
        return combined_result
    
    def _analyze_combined_sufficiency(self, original_query: str, merged_summary: str, 
                                    all_intent_results: List[Dict], iteration: int) -> SufficiencyAnalysis:
        """
        Analyze whether the combined results from graph and RAG are sufficient.
        
        Args:
            original_query: The original user query
            merged_summary: Combined summary from all intents
            all_intent_results: List of all intent results
            iteration: Current iteration number
            
        Returns:
            SufficiencyAnalysis object
        """
        try:
            # Calculate overall success metrics
            successful_intents = sum(1 for result in all_intent_results if result['success'])
            total_graph_records = sum(
                result['graph_result']['records_count'] for result in all_intent_results
                if result['graph_result'] and result['graph_result']['success']
            )
            total_rag_documents = sum(
                result['rag_result']['documents_count'] for result in all_intent_results
                if result['rag_result'] and result['rag_result']['success']
            )
            
            # If no results at all, definitely not sufficient
            if successful_intents == 0 and total_graph_records == 0 and total_rag_documents == 0:
                return SufficiencyAnalysis(
                    sufficient=False,
                    confidence=0.0,
                    missing_info='No results found from either graph database or document search',
                    suggested_followup=original_query
                )
            
            # Use the standard sufficiency analysis prompt with combined results
            combined_results_text = f"""
            Combined Analysis Results: {merged_summary}
            
            Metrics:
            - Successful intents: {successful_intents}/{len(all_intent_results)}
            - Graph database records: {total_graph_records}
            - Relevant documents: {total_rag_documents}
            """
            
            combined_prompt = SUFFICIENCY_ANALYSIS_PROMPT.format(
                original_query=original_query,
                current_results=combined_results_text,
                iteration=iteration,
                max_iterations=self.max_iterations
            )
            
            # Log the sufficiency analysis API call
            start_time = time.time()
            messages = [{"role": "user", "content": combined_prompt}]
            
            response = self.openai_client.chat.completions.parse(
                model=config.openai.model,
                messages=messages,
                temperature=1.0,
                max_completion_tokens=None,
                response_format=SufficiencyAnalysis
            )
            
            # Log the API call details
            duration_ms = (time.time() - start_time) * 1000
            openai_logger.log_api_call(
                method="chat.completions.parse",
                messages=messages,
                model=config.openai.model,
                temperature=1.0,
                max_tokens=None,
                response=response,
                duration_ms=duration_ms,
                agent_name="SufficiencyAgent"
            )
            
            if response.choices[0].message.refusal:
                self.logger.warning(f"Sufficiency analysis refused: {response.choices[0].message.refusal}")
                return SufficiencyAnalysis(
                    sufficient=False,
                    confidence=0.0,
                    missing_info='Analysis was refused for safety reasons',
                    suggested_followup=original_query
                )
            
            analysis = response.choices[0].message.parsed
            return analysis
            
        except Exception as e:
            self.logger.error(f"Combined sufficiency analysis failed: {str(e)}")
            # Default to insufficient if analysis fails
            return SufficiencyAnalysis(
                sufficient=False,
                confidence=0.0,
                missing_info='Unable to analyze combined results sufficiency',
                suggested_followup=original_query
            )
    
    def _create_error_result(self, user_query: str, error_message: str, iterations: List[SearchIteration]) -> SearchResult:
        """
        Create an error result for failed pipeline execution.
        
        Args:
            user_query: The original user query
            error_message: Error message describing the failure
            iterations: Any completed iterations before failure
            
        Returns:
            SearchResult with error information
        """
        return SearchResult(
            original_query=user_query,
            iterations=iterations,
            final_answer=f"Search failed: {error_message}",
            success=False,
            total_execution_time_ms=0.0,
            error_message=error_message,
            records=[]
        )