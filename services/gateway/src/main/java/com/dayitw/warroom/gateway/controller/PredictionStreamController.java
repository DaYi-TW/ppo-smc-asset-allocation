package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.exception.PredictionNotReadyException;
import com.dayitw.warroom.gateway.service.InferenceClient;
import com.dayitw.warroom.gateway.service.PredictionBroadcaster;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/v1/predictions")
public class PredictionStreamController {

    private static final Logger log = LoggerFactory.getLogger(PredictionStreamController.class);
    private static final long SSE_TIMEOUT_MS = 0L;

    private final PredictionBroadcaster broadcaster;
    private final InferenceClient inferenceClient;

    public PredictionStreamController(PredictionBroadcaster broadcaster, InferenceClient inferenceClient) {
        this.broadcaster = broadcaster;
        this.inferenceClient = inferenceClient;
    }

    @GetMapping(path = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream() {
        var emitter = new SseEmitter(SSE_TIMEOUT_MS);
        broadcaster.addClient(emitter);
        try {
            var initial = inferenceClient.getLatest();
            broadcaster.pushInitialState(emitter, initial);
        } catch (PredictionNotReadyException ex) {
            log.debug("predictions.stream.no_initial_state");
        } catch (Exception ex) {
            log.warn("predictions.stream.initial_state_failed error={}", ex.getMessage());
        }
        return emitter;
    }
}
