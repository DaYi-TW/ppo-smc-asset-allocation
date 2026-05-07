package com.dayitw.warroom.gateway.service;

import com.dayitw.warroom.gateway.dto.EpisodeListEnvelopeDto;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.exception.InferenceTimeoutException;
import com.dayitw.warroom.gateway.exception.PredictionNotReadyException;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.time.Duration;

/**
 * Pass-through client for 005 episode endpoints (feature 009).
 *
 * <p>list / detail bodies are forwarded as raw JsonNode to avoid maintaining 14
 * deeply nested DTOs whose only purpose would be to be re-serialised verbatim.
 * The list endpoint still uses a typed envelope so swagger and tests have
 * structure to assert on.</p>
 */
@Service
public class EpisodeClient {

    private final RestClient restClient;
    private final Duration listTimeout;
    private final Duration detailTimeout;

    public EpisodeClient(RestClient inferenceRestClient,
                         @Value("${inference.timeout.episodes-list:5s}") Duration listTimeout,
                         @Value("${inference.timeout.episodes-detail:10s}") Duration detailTimeout) {
        this.restClient = inferenceRestClient;
        this.listTimeout = listTimeout;
        this.detailTimeout = detailTimeout;
    }

    public EpisodeListEnvelopeDto listEpisodes() {
        return doCall(() -> restClient.get().uri("/api/v1/episodes")
                .retrieve()
                .body(EpisodeListEnvelopeDto.class), listTimeout);
    }

    public JsonNode getEpisodeDetail(String episodeId) {
        return doCall(() -> restClient.get().uri("/api/v1/episodes/{id}", episodeId)
                .retrieve()
                .body(JsonNode.class), detailTimeout);
    }

    @SuppressWarnings("unused")
    private <T> T doCall(java.util.function.Supplier<T> action, Duration timeout) {
        try {
            return action.get();
        } catch (HttpClientErrorException.NotFound ex) {
            throw new PredictionNotReadyException("episode not found");
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
