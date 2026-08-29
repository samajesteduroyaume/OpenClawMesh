using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace OpenClawMesh.SDK
{
    public class ChatMessage
    {
        [JsonPropertyName("role")]
        public string Role { get; set; } = "user";

        [JsonPropertyName("content")]
        public string Content { get; set; } = string.Empty;
    }

    public class ChatRequest
    {
        [JsonPropertyName("model")]
        public string Model { get; set; } = "auto";

        [JsonPropertyName("messages")]
        public List<ChatMessage> Messages { get; set; } = new();

        [JsonPropertyName("stream")]
        public bool Stream { get; set; } = false;
    }

    public class ChatResponse
    {
        [JsonPropertyName("id")]
        public string Id { get; set; } = string.Empty;

        [JsonPropertyName("choices")]
        public List<ChoiceItem> Choices { get; set; } = new();
    }

    public class ChoiceItem
    {
        [JsonPropertyName("message")]
        public ChatMessage Message { get; set; } = new();
    }

    public class OpenClawClient
    {
        private readonly string _baseUrl;
        private readonly string _apiKey;
        private readonly HttpClient _httpClient;

        public OpenClawClient(string baseUrl = "http://127.0.0.1:8000", string apiKey = "free-key")
        {
            _baseUrl = baseUrl.TrimEnd('/');
            _apiKey = apiKey;
            _httpClient = new HttpClient();
            _httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
        }

        public async Task<string> CreateChatCompletionAsync(string prompt, string model = "auto")
        {
            var req = new ChatRequest
            {
                Model = model,
                Messages = new List<ChatMessage>
                {
                    new ChatMessage { Role = "user", Content = prompt }
                }
            };

            var jsonContent = new StringContent(JsonSerializer.Serialize(req), Encoding.UTF8, "application/json");
            var response = await _httpClient.PostAsync($"{_baseUrl}/v1/chat/completions", jsonContent);
            response.EnsureSuccessStatusCode();

            var responseBody = await response.Content.ReadAsStringAsync();
            var result = JsonSerializer.Deserialize<ChatResponse>(responseBody);

            return result?.Choices?.Count > 0 ? result.Choices[0].Message.Content : string.Empty;
        }
    }
}
