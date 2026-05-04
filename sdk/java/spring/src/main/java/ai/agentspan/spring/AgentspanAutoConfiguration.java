package ai.agentspan.spring;

import ai.agentspan.AgentConfig;
import ai.agentspan.AgentRuntime;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(AgentspanProperties.class)
public class AgentspanAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AgentConfig agentspanConfig(AgentspanProperties props) {
        return new AgentConfig(
            props.getServerUrl(),
            props.getAuthKey(),
            props.getAuthSecret(),
            props.getWorkerPollIntervalMs(),
            props.getWorkerThreadCount()
        );
    }

    @Bean
    @ConditionalOnMissingBean
    public AgentRuntime agentRuntime(AgentConfig agentConfig) {
        return new AgentRuntime(agentConfig);
    }
}
