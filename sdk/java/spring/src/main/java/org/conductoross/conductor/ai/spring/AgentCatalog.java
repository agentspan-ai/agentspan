package org.conductoross.conductor.ai.spring;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.annotations.AgentDef;
import org.springframework.context.ApplicationContext;
import org.springframework.util.ClassUtils;

/**
 * Catalog of all agents declared via
 * {@link org.conductoross.conductor.ai.annotations.AgentDef @AgentDef} methods on
 * Spring beans.
 *
 * <p>Auto-configured by {@link AgentAutoConfiguration}; inject it anywhere to look
 * up agents by name:
 *
 * <pre>{@code
 * @Component
 * class Crew {
 *     @AgentDef(model = "openai/gpt-4o")
 *     public String support() { return "You handle support tickets."; }
 * }
 *
 * @Service
 * class TicketService {
 *     TicketService(AgentRuntime runtime, AgentCatalog agents) {
 *         runtime.run(agents.get("support"), "My invoice is wrong");
 *     }
 * }
 * }</pre>
 *
 * <p>Beans are scanned lazily on first access (after the context is fully started),
 * and only beans whose class declares {@code @AgentDef} methods are instantiated by
 * the scan. Duplicate agent names across beans fail fast.
 */
public class AgentCatalog {

    private final ApplicationContext context;
    private volatile Map<String, Agent> agents;

    public AgentCatalog(ApplicationContext context) {
        this.context = context;
    }

    /** All agents declared on beans in the context. */
    public List<Agent> all() {
        return new ArrayList<>(scan().values());
    }

    /** Names of all declared agents. */
    public Set<String> names() {
        return scan().keySet();
    }

    /**
     * Look up an agent by name.
     *
     * @throws IllegalArgumentException if no bean declares an agent with that name
     */
    public Agent get(String name) {
        Agent agent = scan().get(name);
        if (agent == null) {
            throw new IllegalArgumentException(
                    "No agent named '" + name + "' declared on any bean. Available: " + scan().keySet());
        }
        return agent;
    }

    /** Look up an agent by name, empty if absent. */
    public Optional<Agent> find(String name) {
        return Optional.ofNullable(scan().get(name));
    }

    private Map<String, Agent> scan() {
        Map<String, Agent> local = agents;
        if (local == null) {
            synchronized (this) {
                local = agents;
                if (local == null) {
                    local = doScan();
                    agents = local;
                }
            }
        }
        return local;
    }

    private Map<String, Agent> doScan() {
        Map<String, Agent> found = new LinkedHashMap<>();
        Map<String, String> sourceBeans = new LinkedHashMap<>();
        for (String beanName : context.getBeanDefinitionNames()) {
            Class<?> type = context.getType(beanName, false);
            if (type == null) continue;
            // Resolve the user class behind a CGLIB proxy; AgentRegistry's
            // hierarchy-walking discovery then finds annotations through the
            // proxy subclass when resolving the bean itself.
            if (!declaresAgentDefs(ClassUtils.getUserClass(type))) continue;

            for (Agent agent : Agent.fromInstance(context.getBean(beanName))) {
                String previous = sourceBeans.putIfAbsent(agent.getName(), beanName);
                if (previous != null) {
                    throw new IllegalStateException("Duplicate agent name '" + agent.getName() + "' declared by beans '"
                            + previous + "' and '" + beanName + "'");
                }
                found.put(agent.getName(), agent);
            }
        }
        return Collections.unmodifiableMap(found);
    }

    /** True if the class (or any ancestor/interface) declares an @AgentDef method. */
    private static boolean declaresAgentDefs(Class<?> type) {
        if (type == null || type == Object.class) return false;
        for (Method method : type.getDeclaredMethods()) {
            if (method.isAnnotationPresent(AgentDef.class)) return true;
        }
        for (Class<?> iface : type.getInterfaces()) {
            if (declaresAgentDefs(iface)) return true;
        }
        return declaresAgentDefs(type.getSuperclass());
    }
}
