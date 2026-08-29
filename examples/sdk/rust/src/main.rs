use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::error::Error;

#[derive(Debug, Serialize)]
struct InferenceRequest {
    model: String,
    messages: Vec<ChatMessage>,
    stream: bool,
}

#[derive(Debug, Serialize, Deserialize)]
struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct ChatChoice {
    message: ChatMessage,
}

#[derive(Debug, Deserialize)]
struct InferenceResponse {
    id: String,
    choices: Vec<ChatChoice>,
}

pub struct OpenClawClient {
    base_url: String,
    api_key: String,
    client: Client,
}

impl OpenClawClient {
    pub fn new(base_url: &str, api_key: &str) -> Self {
        Self {
            base_url: base_url.to_string(),
            api_key: api_key.to_string(),
            client: Client::new(),
        }
    }

    pub async fn chat_completion(&self, model: &str, prompt: &str) -> Result<String, Box<dyn Error>> {
        let url = format!("{}/v1/chat/completions", self.base_url);
        let req = InferenceRequest {
            model: model.to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: prompt.to_string(),
            }],
            stream: false,
        };

        let res = self
            .client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .json(&req)
            .send()
            .await?;

        let parsed: InferenceResponse = res.json().await?;
        if let Some(first) = parsed.choices.first() {
            Ok(first.message.content.clone())
        } else {
            Ok("".to_string())
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    println!("🦀 Initializing OpenClawMesh Rust Client...");
    let client = OpenClawClient::new("http://127.0.0.1:8000", "free-tier-key");
    
    let answer = client.chat_completion("auto", "Explain OpenClawMesh decentralization").await?;
    println!("Response from Mesh:\n{}", answer);
    Ok(())
}
