/**
 * OpenClawMesh Client SDK — TypeScript / Node.js
 *
 * Client léger pour interagir avec le réseau P2P et la passerelle d'inférence OpenClawMesh :
 * - Inférence Chat Completions (REST & Streaming SSE)
 * - Exécution de compétences / Tool Calling
 * - Récupération des métriques et des modèles disponibles
 */

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ChatOptions {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  stream?: boolean;
}

export interface SkillExecutionResult {
  ok: boolean;
  result: any;
  skill: string;
  duration_ms: number;
}

export class OpenClawMeshClient {
  private baseUrl: string;
  private apiKey?: string;

  constructor(options: { baseUrl?: string; apiKey?: string } = {}) {
    this.baseUrl = (options.baseUrl || 'http://localhost:8000').replace(/\/$/, '');
    this.apiKey = options.apiKey;
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
      headers['X-API-Key'] = this.apiKey;
    }
    return headers;
  }

  /**
   * Obtient instantanément une clé gratuite d'accès communautaire.
   */
  async getFreeApiKey(email?: string): Promise<{ apiKey: string; plan: string }> {
    const res = await fetch(`${this.baseUrl}/api/v1/checkout/free-key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email || '' }),
    });
    if (!res.ok) throw new Error(`Échec génération clé: ${res.statusText}`);
    const data = await res.json();
    this.apiKey = data.api_key;
    return { apiKey: data.api_key, plan: data.plan };
  }

  /**
   * Liste les modèles d'IA disponibles sur le maillage.
   */
  async listModels(): Promise<Array<{ id: string; owned_by: string }>> {
    const res = await fetch(`${this.baseUrl}/v1/models`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error(`Échec listage modèles: ${res.statusText}`);
    const data = await res.json();
    return data.data;
  }

  /**
   * Exécute une requête Chat Completion.
   */
  async chat(messages: ChatMessage[], options: ChatOptions = {}): Promise<string> {
    const res = await fetch(`${this.baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        messages,
        model: options.model || 'qwen2.5-coder-7b',
        stream: false,
      }),
    });
    if (!res.ok) throw new Error(`Échec inférence chat: ${res.statusText}`);
    const data = await res.json();
    return data.choices?.[0]?.message?.content || '';
  }

  /**
   * Exécute une compétence spécifique (ex: llm, memory_search, echo).
   */
  async executeSkill(skill: string, payload: Record<string, any> = {}): Promise<SkillExecutionResult> {
    const res = await fetch(`${this.baseUrl}/api/v1/execute`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ skill, payload }),
    });
    if (!res.ok) throw new Error(`Échec exécution compétence: ${res.statusText}`);
    return (await res.json()) as SkillExecutionResult;
  }

  /**
   * Récupère le statut complet et les métriques de santé du cluster.
   */
  async getClusterStatus(): Promise<any> {
    const res = await fetch(`${this.baseUrl}/api/v1/cluster/status`);
    if (!res.ok) throw new Error(`Échec cluster status: ${res.statusText}`);
    return await res.json();
  }
}
