// server/src/test/java/dev/agentspan/runtime/util/JavaScriptBuilderSignalTest.java
package dev.agentspan.runtime.util;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class JavaScriptBuilderSignalTest {

    @Test
    void signalIntakeScript_evaluate_returnsNonEmpty() {
        String script = JavaScriptBuilder.signalIntakeScript("evaluate");
        assertThat(script).isNotBlank();
        assertThat(script).contains("pending").contains("evaluate");
    }

    @Test
    void signalIntakeScript_autoAccept_returnsAutoAcceptLogic() {
        String script = JavaScriptBuilder.signalIntakeScript("auto_accept");
        assertThat(script).contains("auto_accept");
    }

    @Test
    void signalDispositionScript_accept_containsAcceptLogic() {
        String script = JavaScriptBuilder.signalDispositionScript("accept_signal");
        assertThat(script).contains("accepted").contains("updatedProcessing");
    }

    @Test
    void signalDispositionScript_reject_containsRejectLogic() {
        String script = JavaScriptBuilder.signalDispositionScript("reject_signal");
        assertThat(script).contains("rejected").contains("rejectionReason");
    }

    @Test
    void signalDispositionScript_acceptAll_containsAcceptAllLogic() {
        String script = JavaScriptBuilder.signalDispositionScript("accept_all_signals");
        assertThat(script).contains("count").contains("updatedProcessed");
    }

    @Test
    void implicitAcceptScript_returnsScript() {
        String script = JavaScriptBuilder.implicitAcceptScript();
        assertThat(script).contains("accepted_implicit").contains("newDispositions");
    }

    @Test
    void signalStateMergeScript_returnsScript() {
        String script = JavaScriptBuilder.signalStateMergeScript();
        assertThat(script).contains("newDispositions").contains("joinOutput");
    }
}
