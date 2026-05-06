package com.dayitw.warroom.gateway.service;

import com.dayitw.warroom.gateway.dto.HealthDto;
import com.dayitw.warroom.gateway.dto.PredictionPayloadDto;
import com.dayitw.warroom.gateway.exception.InferenceBusyException;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.exception.InferenceTimeoutException;
import com.dayitw.warroom.gateway.exception.PredictionNotReadyException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.time.Duration;

@Service
public class InferenceClient {

    private final RestClient restClient;
    private final Duration runTimeout;
    private final Duration latestTimeout;
    private final Duration healthzTimeout;

    public InferenceClient(RestClient inferenceRestClient,
                           @Value("${inference.timeout.run:90s}") Duration runTimeout,
                           @Value("${inference.timeout.latest:5s}") Duration latestTimeout,
                           @Value("${inference.timeout.healthz:2s}") Duration healthzTimeout) {
        this.restClient = inferenceRestClient;
        this.runTimeout = runTimeout;
        this.latestTimeout = latestTimeout;
        this.healthzTimeout = healthzTimeout;
    }

    public PredictionPayloadDto runInference() {
        return doCall(() -> restClient.post().uri("/infer/run")
                .retrieve()
                .body(PredictionPayloadDto.class), runTimeout);
    }

    public PredictionPayloadDto getLatest() {
        return doCall(() -> restClient.get().uri("/infer/latest")
                .retrieve()
                .body(PredictionPayloadDto.class), latestTimeout);
    }

    public HealthDto getHealthz() {
        return doCall(() -> restClient.get().uri("/healthz")
                .retrieve()
                .body(HealthDto.class), healthzTimeout);
    }

    @SuppressWarnings("unused")
    private <T> T doCall(java.util.function.Supplier<T> action, Duration timeout) {
        try {
            return action.get();
        } catch (HttpClientErrorException.NotFound ex) {
            throw new PredictionNotReadyException("upstream 404");
        } catch (HttpClientErrorException.Conflict ex) {
            throw new InferenceBusyException("upstream 409");
        } catch (HttpClientErrorException ex) {
            throw new InferenceServiceException("upstream 4xx: " + ex.getStatusCode(), ex);
        } catch (HttpServerErrorException ex) {
            throw new InferenceServiceException("upstream 5xx: " + ex.getStatusCode(), ex);
        } catch (ResourceAccessException ex) {
            if (ex.getCause() instanceof java.net.SocketTimeoutException) {
                throw new InferenceTimeoutException("upstream timeout", ex);
            }
            throw new InferenceServiceException("upstream connection error", ex);
        } catch (RestClientException ex) {
            throw new InferenceServiceException("upstream call failed", ex);
        }
    }
}
