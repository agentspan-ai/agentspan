// server/src/main/java/dev/agentspan/runtime/model/SignalReceipt.java
package dev.agentspan.runtime.model;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class SignalReceipt {
    private final String signalId;
    private final String executionId;
    private final String status;

    public SignalReceipt(String signalId, String executionId, String status) {
        this.signalId = signalId;
        this.executionId = executionId;
        this.status = status;
    }

    public String getSignalId() { return signalId; }
    public String getExecutionId() { return executionId; }
    public String getStatus() { return status; }
}
