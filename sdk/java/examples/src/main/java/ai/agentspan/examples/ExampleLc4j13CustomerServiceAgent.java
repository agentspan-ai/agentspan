// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Example Lc4j 13 — Customer Service Agent
 *
 * <p>Java port of <code>sdk/python/examples/langchain/13_customer_service_agent.py</code>.
 *
 * <p>Demonstrates: domain-specific tools (order lookup, FAQ search, ticket
 * creation) bundled into a customer service persona with a system prompt.
 */
public class ExampleLc4j13CustomerServiceAgent {

    static class CustomerServiceTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "lookup_order",
            value = "Look up the status and details of a customer order. "
                  + "Args: order_id: The order ID (e.g., 'ORD-12345')."
        )
        public String lookupOrder(@dev.langchain4j.agent.tool.P("order_id") String orderId) {
            Map<String, String> orders = new LinkedHashMap<>();
            orders.put("ORD-12345", "Status: Shipped. Carrier: FedEx. Tracking: 9612345. Expected delivery: 2 days.");
            orders.put("ORD-67890", "Status: Processing. Payment confirmed. Estimated ship date: tomorrow.");
            orders.put("ORD-11111", "Status: Delivered. Delivered on 2025-03-15 at 2:34 PM. Signed by: J. Smith.");
            orders.put("ORD-99999", "Status: Cancelled. Refund of $49.99 issued on 2025-03-10.");
            String key = orderId == null ? "" : orderId.toUpperCase();
            return orders.getOrDefault(key, "Order '" + orderId + "' not found. Please verify the order ID.");
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "search_faq",
            value = "Search the FAQ knowledge base for answers to common questions. "
                  + "Args: question: The customer's question or keyword."
        )
        public String searchFaq(@dev.langchain4j.agent.tool.P("question") String question) {
            Map<String, String> faq = new LinkedHashMap<>();
            faq.put("return",
                "Returns are accepted within 30 days of delivery. Items must be unused and in original packaging. "
                + "Start a return at returns.example.com.");
            faq.put("refund",
                "Refunds are processed within 5-7 business days after we receive the returned item.");
            faq.put("shipping",
                "Standard shipping: 3-5 days ($4.99). Express: 1-2 days ($12.99). "
                + "Free standard shipping on orders over $50.");
            faq.put("cancel",
                "Orders can be cancelled within 1 hour of placement. After that, please wait for delivery "
                + "and then initiate a return.");
            faq.put("warranty",
                "All products carry a 1-year manufacturer warranty. Extended warranty plans are available "
                + "for electronics.");
            String q = question == null ? "" : question.toLowerCase();
            for (Map.Entry<String, String> entry : faq.entrySet()) {
                if (q.contains(entry.getKey())) return entry.getValue();
            }
            return "No FAQ entry matched your question. A support representative will follow up within 24 hours.";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "create_support_ticket",
            value = "Create a support ticket for issues requiring human review. "
                  + "Args: issue: Description of the customer's issue. "
                  + "priority: Ticket priority — 'low', 'normal', or 'high'."
        )
        public String createSupportTicket(
                @dev.langchain4j.agent.tool.P("issue") String issue,
                @dev.langchain4j.agent.tool.P("priority") String priority) {
            String pri = priority == null || priority.isEmpty() ? "normal" : priority;
            int ticketNum = ThreadLocalRandom.current().nextInt(10000, 100000);
            String ticketId = "TKT-" + ticketNum;
            String contactSla = "high".equals(pri) ? "4 hours" : "24 hours";
            String preview = issue == null ? "" : (issue.length() > 100 ? issue.substring(0, 100) : issue);
            return "Support ticket " + ticketId + " created (priority: " + pri + "). "
                + "A representative will contact you within " + contactSla + ". "
                + "Issue: " + preview;
        }
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "customer_service_agent",
            Settings.LLM_MODEL,
            "You are Alex, a friendly and professional customer service agent for ShopEasy. "
            + "Always greet the customer warmly. Use tools to look up orders and answer questions. "
            + "If you cannot resolve the issue, escalate by creating a support ticket. "
            + "Keep responses concise and empathetic.",
            new CustomerServiceTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Hi, I ordered something 5 days ago. My order ID is ORD-12345. Where is my package?"
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
