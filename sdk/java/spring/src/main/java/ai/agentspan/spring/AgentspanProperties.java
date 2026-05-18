package ai.agentspan.spring;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "agentspan")
public class AgentspanProperties {

    private String serverUrl = "http://localhost:6767";
    private String authKey;
    private String authSecret;
    private int workerPollIntervalMs = 100;
    private int workerThreadCount = 1;

    public String getServerUrl() { return serverUrl; }
    public void setServerUrl(String serverUrl) { this.serverUrl = serverUrl; }

    public String getAuthKey() { return authKey; }
    public void setAuthKey(String authKey) { this.authKey = authKey; }

    public String getAuthSecret() { return authSecret; }
    public void setAuthSecret(String authSecret) { this.authSecret = authSecret; }

    public int getWorkerPollIntervalMs() { return workerPollIntervalMs; }
    public void setWorkerPollIntervalMs(int workerPollIntervalMs) { this.workerPollIntervalMs = workerPollIntervalMs; }

    public int getWorkerThreadCount() { return workerThreadCount; }
    public void setWorkerThreadCount(int workerThreadCount) { this.workerThreadCount = workerThreadCount; }
}
