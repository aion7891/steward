// AI model: provider and model; installed Ollama models are listed with "can use tools".
import { Cpu, Save } from "lucide-react";
import { useEffect, useState } from "react";

import { formatBytes } from "../../utils/format.js";
import Alert from "../ui/Alert.jsx";
import Badge from "../ui/Badge.jsx";
import Button from "../ui/Button.jsx";
import Card from "../ui/Card.jsx";
import LockedNote from "./LockedNote.jsx";

function OllamaModelList({ models, selected, onPick }) {
  return (
    <ul className="model-list">
      {models.filter((m) => !m.embedding).map((model) => (
        <li key={model.name}>
          <button type="button" className={`model-option ${selected === model.name ? "model-option--active" : ""}`}
            disabled={!model.tools} onClick={() => onPick(model.name)}
            title={model.tools ? "Select this model" : "This model cannot use tools, so Steward's agents would fail"}>
            <span className="mono">{model.name}</span>
            <span className="row">
              {model.tools ? <Badge tone="success">can use tools</Badge> : <Badge tone="danger">no tools</Badge>}
              {model.cloud ? (
                <Badge tone="warning" title="Runs on Ollama's servers: your questions leave this computer">cloud</Badge>
              ) : (
                <span className="faint">{formatBytes(model.size_bytes)}</span>
              )}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function ModelSettings({ settings, models, saving, onSave }) {
  const current = settings.models || {};
  const [provider, setProvider] = useState(current.provider || "ollama");
  const [modelId, setModelId] = useState(current.model_id || "");
  useEffect(() => {
    setProvider(current.provider || "ollama");
    setModelId(current.model_id || "");
  }, [current.provider, current.model_id]);

  const locked = (settings.locked && (settings.locked.model_id || settings.locked.provider)) || null;
  const ollama = (models && models.ollama) || { reachable: false, models: [] };
  const changed = provider !== current.provider || modelId !== current.model_id;
  const providers = (models && models.providers) || ["ollama", "openai", "anthropic", "gemini"];

  return (
    <Card title="AI model" subtitle="The brain behind chat and the agents"
      actions={<Badge tone="neutral" icon={Cpu}>{current.provider} / {current.model_id}</Badge>}>
      <div className="stack">
        {locked && <LockedNote variable={locked} />}
        <div>
          <label className="label" htmlFor="provider">Provider</label>
          <select id="provider" className="input" value={provider} disabled={Boolean(locked)}
            onChange={(e) => setProvider(e.target.value)}>
            {providers.map((p) => <option key={p} value={p}>{p === "ollama" ? "Ollama (on this computer)" : `${p} (cloud)`}</option>)}
          </select>
        </div>
        {provider === "ollama" && !ollama.reachable && (
          <Alert tone="warning">Ollama is not reachable at {ollama.host}. Start it with <code>ollama serve</code>.</Alert>
        )}
        {provider === "ollama" && ollama.reachable ? (
          <OllamaModelList models={ollama.models} selected={modelId} onPick={setModelId} />
        ) : (
          <div>
            <label className="label" htmlFor="model-id">Model name</label>
            <input id="model-id" className="input mono" value={modelId} disabled={Boolean(locked)}
              onChange={(e) => setModelId(e.target.value)} placeholder="e.g. gpt-4o-mini" />
          </div>
        )}
        {provider !== "ollama" && (
          <Alert tone="warning">Cloud models send your questions and document snippets off this computer.</Alert>
        )}
        <div>
          <Button variant="primary" icon={Save} loading={saving} disabled={!changed || Boolean(locked) || !modelId}
            onClick={() => onSave({ provider, model_id: modelId }, `Now using ${provider} / ${modelId}.`)}>
            Save model
          </Button>
        </div>
      </div>
    </Card>
  );
}
