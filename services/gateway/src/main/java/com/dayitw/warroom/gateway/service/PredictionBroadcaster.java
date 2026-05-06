package com.dayitw.warroom.gateway.service;

import com.dayitw.warroom.gateway.dto.PredictionEventDto;
import com.dayitw.warroom.gateway.dto.PredictionPayloadDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

@Service
public class PredictionBroadcaster implements MessageListener {

    private static final Logger log = LoggerFactory.getLogger(PredictionBroadcaster.class);
    private final CopyOnWriteArrayList<SseEmitter> clients = new CopyOnWriteArrayList<>();
    private final InferenceClient inferenceClient;
    private final ObjectMapper objectMapper;

    public PredictionBroadcaster(InferenceClient inferenceClient, ObjectMapper objectMapper) {
        this.inferenceClient = inferenceClient;
        this.objectMapper = objectMapper;
    }

    public void addClient(SseEmitter emitter) {
        clients.add(emitter);
        emitter.onCompletion(() -> removeClient(emitter));
        emitter.onTimeout(() -> removeClient(emitter));
        emitter.onError(t -> removeClient(emitter));
    }

    public void removeClient(SseEmitter emitter) {
        clients.remove(emitter);
    }

    public int clientCount() {
        return clients.size();
    }

    public void pushInitialState(SseEmitter emitter, PredictionPayloadDto payload) {
        sendOne(emitter, predictionEvent(payload));
    }

    public void broadcast(PredictionPayloadDto payload) {
        var event = predictionEvent(payload);
        sendToAll(event);
    }

    @Override
    public void onMessage(Message message, byte[] pattern) {
        try {
            var payload = objectMapper.readValue(message.getBody(), PredictionPayloadDto.class);
            broadcast(payload);
        } catch (IOException ex) {
            log.warn("predictions.broadcast.malformed_payload error={}", ex.getMessage());
        }
    }

    public void sendKeepAlive() {
        for (SseEmitter emitter : List.copyOf(clients)) {
            try {
                emitter.send(SseEmitter.event().comment("ping"));
            } catch (Exception ex) {
                removeClient(emitter);
            }
        }
    }

    @Scheduled(fixedDelayString = "${predictions.sse.keep-alive-interval-seconds:15}000")
    void scheduledKeepAlive() {
        sendKeepAlive();
    }

    private PredictionEventDto predictionEvent(PredictionPayloadDto payload) {
        return new PredictionEventDto("prediction", Instant.now().toString(), payload);
    }

    private void sendToAll(PredictionEventDto event) {
        for (SseEmitter emitter : List.copyOf(clients)) {
            sendOne(emitter, event);
        }
    }

    private void sendOne(SseEmitter emitter, PredictionEventDto event) {
        try {
            emitter.send(SseEmitter.event().name(event.eventType()).data(event));
        } catch (Exception ex) {
            log.debug("predictions.broadcast.send_failed remove emitter={}", emitter);
            removeClient(emitter);
        }
    }
}
