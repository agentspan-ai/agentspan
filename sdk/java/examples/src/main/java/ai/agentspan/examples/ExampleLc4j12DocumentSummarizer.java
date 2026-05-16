// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.ArrayList;
import java.util.List;

/**
 * Example Lc4j 12 — Document Summarizer
 *
 * <p>Java port of <code>sdk/python/examples/langchain/12_document_summarizer.py</code>.
 *
 * <p>Demonstrates: chunking, sentence counting, and key-sentence extraction over
 * long documents using three LangChain4j tools.
 */
public class ExampleLc4j12DocumentSummarizer {

    static class DocumentSummarizerTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "split_into_chunks",
            value = "Split a document into chunks of approximately chunk_size words. "
                  + "Args: text: The full document text. "
                  + "chunk_size: Target words per chunk (default 200)."
        )
        public String splitIntoChunks(
                @dev.langchain4j.agent.tool.P("text") String text,
                @dev.langchain4j.agent.tool.P("chunk_size") int chunkSize) {
            int cs = chunkSize <= 0 ? 200 : chunkSize;
            String[] words = text.trim().isEmpty()
                ? new String[0]
                : text.trim().split("\\s+");
            List<String> chunks = new ArrayList<>();
            for (int i = 0; i < words.length; i += cs) {
                int end = Math.min(i + cs, words.length);
                StringBuilder sb = new StringBuilder();
                for (int j = i; j < end; j++) {
                    if (j > i) sb.append(" ");
                    sb.append(words[j]);
                }
                chunks.add(sb.toString());
            }
            if (chunks.isEmpty()) return "Empty document.";
            String first = chunks.get(0);
            String preview = first.length() > 150 ? first.substring(0, 150) : first;
            return "Split into " + chunks.size() + " chunk(s).\nChunk 1 preview: " + preview + "...";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "count_sentences",
            value = "Count sentences and estimate reading time for a document. "
                  + "Args: text: The document text to analyze."
        )
        public String countSentences(@dev.langchain4j.agent.tool.P("text") String text) {
            String normalized = text.replace("!", ".").replace("?", ".");
            String[] raw = normalized.split("\\.");
            int sentenceCount = 0;
            for (String s : raw) {
                if (!s.trim().isEmpty()) sentenceCount++;
            }
            int words = text.trim().isEmpty() ? 0 : text.trim().split("\\s+").length;
            int readingTime = Math.max(1, words / 200);
            return "Sentences: " + sentenceCount + ", Words: " + words
                + ", Estimated reading time: ~" + readingTime + " minute(s).";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "extract_key_sentences",
            value = "Extract the n most informative sentences from a document. "
                  + "Selects sentences that are long enough to be informative. "
                  + "Args: text: The document text. "
                  + "n: Number of key sentences to extract (default 3)."
        )
        public String extractKeySentences(
                @dev.langchain4j.agent.tool.P("text") String text,
                @dev.langchain4j.agent.tool.P("n") int n) {
            int limit = n <= 0 ? 3 : n;
            String flat = text.replace("\n", " ");
            String[] raw = flat.split("\\.");
            List<String> sentences = new ArrayList<>();
            for (String s : raw) {
                String t = s.trim();
                if (t.length() > 40) sentences.add(t);
            }
            int take = Math.min(limit, sentences.size());
            if (take == 0) return "No long enough sentences found.";
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < take; i++) {
                if (i > 0) sb.append("\n");
                sb.append(i + 1).append(". ").append(sentences.get(i)).append(".");
            }
            return sb.toString();
        }
    }

    private static final String SAMPLE_DOCUMENT = "\n"
            + "Artificial intelligence is transforming industries at an unprecedented pace. Machine learning\n"
            + "algorithms can now diagnose diseases with accuracy rivaling specialists. Natural language\n"
            + "processing has enabled chatbots and virtual assistants that handle millions of customer\n"
            + "interactions daily. Computer vision systems inspect manufactured goods, detect security\n"
            + "threats, and enable self-driving vehicles. The economic impact is estimated at trillions\n"
            + "of dollars over the next decade. However, these advances also raise concerns about job\n"
            + "displacement, algorithmic bias, and the concentration of AI capabilities in a few large\n"
            + "corporations. Governments worldwide are drafting regulations to ensure AI is developed\n"
            + "safely and equitably. Researchers emphasize that explainability — the ability to understand\n"
            + "why an AI made a decision — is critical for trust and accountability. The field of AI ethics\n"
            + "has grown substantially, attracting philosophers, sociologists, and legal scholars alongside\n"
            + "computer scientists.\n";

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "document_summarizer_agent",
            Settings.LLM_MODEL,
            "You are a document analysis assistant. Use tools to analyze document structure, "
            + "then synthesize a concise summary with key takeaways.",
            new DocumentSummarizerTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Analyze and summarize this document:\n\n" + SAMPLE_DOCUMENT
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
