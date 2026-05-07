package com.dayitw.warroom.gateway.service;

import com.dayitw.warroom.gateway.dto.ContextDto;
import com.dayitw.warroom.gateway.dto.PredictionPayloadDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.Message;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class PredictionBroadcasterTest {

    private InferenceClient inferenceClient;
    private PredictionBroadcaster broadcaster;
    private final ObjectMapper mapper = new ObjectMapper();

    private final PredictionPayloadDto samplePayload = new PredictionPayloadDto(
            "2026-04-28", "next session", "/p.zip", true,
            Map.of("CASH", 1.0), false, false,
            new ContextDto("data/raw", true, 100, 1.0),
            "scheduled", "550e8400-e29b-41d4-a716-446655440000",
            "2026-05-06T00:00:00Z");

    @BeforeEach
    void setup() {
        inferenceClient = mock(InferenceClient.class);
        broadcaster = new PredictionBroadcaster(inferenceClient, mapper);
    }

    @Test
    void addClient_thenBroadcast_emitterReceivesEvent() throws Exception {
        var emitter = new CountingEmitter();
        broadcaster.addClient(emitter);
        broadcaster.broadcast(samplePayload);
        assertThat(emitter.sendCount.get()).isGreaterThanOrEqualTo(1);
    }

    @Test
    void hundredEmitters_allReceiveBroadcast() {
        var emitters = IntStream.range(0, 100).mapToObj(i -> new CountingEmitter()).toList();
        emitters.forEach(broadcaster::addClient);
        broadcaster.broadcast(samplePayload);
        assertThat(emitters).allMatch(e -> e.sendCount.get() >= 1);
    }

    @Test
    void brokenEmitter_isRemoved_othersStillReceive() {
        var broken = new CountingEmitter() {
            @Override
            public void send(SseEventBuilder builder) throws IOException {
                throw new IOException("client gone");
            }
        };
        var healthy = new CountingEmitter();
        broadcaster.addClient(broken);
        broadcaster.addClient(healthy);
        broadcaster.broadcast(samplePayload);
        broadcaster.broadcast(samplePayload);
        assertThat(healthy.sendCount.get()).isEqualTo(2);
        assertThat(broadcaster.clientCount()).isEqualTo(1);
    }

    @Test
    void onMessage_validJson_fansOutToClients() throws Exception {
        var emitter = new CountingEmitter();
        broadcaster.addClient(emitter);

        String json = mapper.writeValueAsString(Map.ofEntries(
                Map.entry("as_of_date", "2026-04-28"),
                Map.entry("next_trading_day_target", "next"),
                Map.entry("policy_path", "/p.zip"),
                Map.entry("deterministic", true),
                Map.entry("target_weights", Map.of("CASH", 1.0)),
                Map.entry("weights_capped", false),
                Map.entry("renormalized", false),
                Map.entry("context", Map.of("data_root", "data/raw", "include_smc", true,
                        "n_warmup_steps", 100, "current_nav_at_as_of", 1.0)),
                Map.entry("triggered_by", "scheduled"),
                Map.entry("inference_id", "550e8400-e29b-41d4-a716-446655440000"),
                Map.entry("inferred_at_utc", "2026-05-06T00:00:00Z")));

        Message msg = mock(Message.class);
        when(msg.getBody()).thenReturn(json.getBytes());
        broadcaster.onMessage(msg, "predictions:latest".getBytes());
        assertThat(emitter.sendCount.get()).isGreaterThanOrEqualTo(1);
    }

    @Test
    void onMessage_malformedJson_doesNotCrashOrDisruptSubscription() {
        var emitter = new CountingEmitter();
        broadcaster.addClient(emitter);

        Message msg = mock(Message.class);
        when(msg.getBody()).thenReturn("{not valid json".getBytes());

        broadcaster.onMessage(msg, "predictions:latest".getBytes());
        assertThat(broadcaster.clientCount()).isEqualTo(1);
    }

    @Test
    void keepAlive_sendsPingToAllEmitters() {
        var emitter = new CountingEmitter();
        broadcaster.addClient(emitter);
        broadcaster.sendKeepAlive();
        assertThat(emitter.sendCount.get()).isGreaterThanOrEqualTo(1);
    }

    static class CountingEmitter extends SseEmitter {
        AtomicInteger sendCount = new AtomicInteger();
        @Override
        public void send(SseEventBuilder builder) throws IOException {
            sendCount.incrementAndGet();
        }
    }
}
