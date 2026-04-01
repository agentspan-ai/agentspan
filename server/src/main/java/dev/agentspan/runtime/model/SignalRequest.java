// server/src/main/java/dev/agentspan/runtime/model/SignalRequest.java
package dev.agentspan.runtime.model;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class SignalRequest {
    private String message;
    private Object data;
    private String priority = "normal";  // "normal" | "urgent"
    private String sender;
    private boolean propagate = true;

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public Object getData() { return data; }
    public void setData(Object data) { this.data = data; }
    public String getPriority() { return priority; }
    public void setPriority(String priority) { this.priority = priority; }
    public String getSender() { return sender; }
    public void setSender(String sender) { this.sender = sender; }
    public boolean isPropagate() { return propagate; }
    public void setPropagate(boolean propagate) { this.propagate = propagate; }
}
