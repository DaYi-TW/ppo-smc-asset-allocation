package com.dayitw.warroom.gateway.service;

import com.dayitw.warroom.gateway.dto.HealthDto;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.exception.InferenceTimeoutException;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class InferenceHealthIndicatorTest {

    @Test
    void healthz_ok_returnsUp_withLatency() {
        var client = mock(InferenceClient.class);
        when(client.getHealthz()).thenReturn(new HealthDto("ok", 100, true, true, null, null));
        var indicator = new InferenceHealthIndicator(client, "http://infer:8000");

        var health = indicator.health();
        assertThat(health.getStatus()).isEqualTo(Status.UP);
        assertThat(health.getDetails()).containsKey("latencyMs");
        assertThat(health.getDetails()).containsEntry("url", "http://infer:8000");
    }

    @Test
    void healthz_timeout_returnsDown() {
        var client = mock(InferenceClient.class);
        when(client.getHealthz()).thenThrow(new InferenceTimeoutException("2s"));
        var indicator = new InferenceHealthIndicator(client, "http://infer:8000");

        var health = indicator.health();
        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
        assertThat(health.getDetails()).containsKey("error");
    }

    @Test
    void healthz_5xx_returnsDown() {
        var client = mock(InferenceClient.class);
        when(client.getHealthz()).thenThrow(new InferenceServiceException("503"));
        var indicator = new InferenceHealthIndicator(client, "http://infer:8000");

        assertThat(indicator.health().getStatus()).isEqualTo(Status.DOWN);
    }
}
