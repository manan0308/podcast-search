"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Key,
  Check,
  AlertTriangle,
  Loader2,
  Eye,
  EyeOff,
  Save,
  Info,
  Trash2,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Provider } from "@/lib/types";

interface ApiKeyConfig {
  name: string;
  envVar: string;
  description: string;
  placeholder: string;
  docsUrl: string;
  required: boolean;
}

const API_KEYS: ApiKeyConfig[] = [
  {
    name: "OpenAI",
    envVar: "OPENAI_API_KEY",
    description: "Required for embeddings (semantic search). Powers the search functionality.",
    placeholder: "sk-...",
    docsUrl: "https://platform.openai.com/api-keys",
    required: true,
  },
  {
    name: "Anthropic",
    envVar: "ANTHROPIC_API_KEY",
    description: "Required for RAG chat (Claude) and speaker labeling.",
    placeholder: "sk-ant-...",
    docsUrl: "https://console.anthropic.com/",
    required: true,
  },
  {
    name: "AssemblyAI",
    envVar: "ASSEMBLYAI_API_KEY",
    description: "Cloud transcription with speaker diarization. $0.37/hour.",
    placeholder: "your-api-key",
    docsUrl: "https://www.assemblyai.com/dashboard/",
    required: false,
  },
  {
    name: "Deepgram",
    envVar: "DEEPGRAM_API_KEY",
    description: "Fast cloud transcription with diarization. $0.26/hour.",
    placeholder: "your-api-key",
    docsUrl: "https://console.deepgram.com/",
    required: false,
  },
];

interface KeyStatus {
  name: string;
  env_var: string;
  configured: boolean;
  masked_value: string | null;
}

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [keyStatuses, setKeyStatuses] = useState<KeyStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [validating, setValidating] = useState<string | null>(null);
  const [validationResults, setValidationResults] = useState<Record<string, { valid: boolean; error?: string }>>({});
  
  // Input values for each key
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [showInputs, setShowInputs] = useState<Record<string, boolean>>({});
  const [editMode, setEditMode] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [providersRes, keysRes] = await Promise.all([
        api.getProviders(),
        api.getApiKeyStatus(),
      ]);
      setProviders(providersRes.providers);
      setKeyStatuses(keysRes);
    } catch (error) {
      console.error("Failed to load settings:", error);
    } finally {
      setLoading(false);
    }
  };

  const getKeyStatus = (envVar: string) => {
    return keyStatuses.find((k) => k.env_var === envVar);
  };

  const handleValidate = async (envVar: string) => {
    const value = keyInputs[envVar];
    if (!value) return;

    setValidating(envVar);
    setValidationResults((prev) => ({ ...prev, [envVar]: undefined as any }));

    try {
      const result = await api.validateApiKey(envVar, value);
      setValidationResults((prev) => ({ ...prev, [envVar]: result }));
    } catch (error) {
      setValidationResults((prev) => ({
        ...prev,
        [envVar]: { valid: false, error: "Validation failed" },
      }));
    } finally {
      setValidating(null);
    }
  };

  const handleSave = async (envVar: string) => {
    const value = keyInputs[envVar];
    if (!value) return;

    setSaving(envVar);

    try {
      await api.updateApiKey(envVar, value);
      // Reload status
      const keysRes = await api.getApiKeyStatus();
      setKeyStatuses(keysRes);
      // Clear input and exit edit mode
      setKeyInputs((prev) => ({ ...prev, [envVar]: "" }));
      setEditMode((prev) => ({ ...prev, [envVar]: false }));
      setValidationResults((prev) => ({ ...prev, [envVar]: undefined as any }));
      // Reload providers to update availability
      const providersRes = await api.getProviders();
      setProviders(providersRes.providers);
    } catch (error) {
      console.error("Failed to save API key:", error);
    } finally {
      setSaving(null);
    }
  };

  const handleDelete = async (envVar: string) => {
    if (!confirm(`Are you sure you want to remove the ${envVar} key?`)) return;

    setSaving(envVar);

    try {
      await api.deleteApiKey(envVar);
      // Reload status
      const keysRes = await api.getApiKeyStatus();
      setKeyStatuses(keysRes);
      // Reload providers
      const providersRes = await api.getProviders();
      setProviders(providersRes.providers);
    } catch (error) {
      console.error("Failed to delete API key:", error);
    } finally {
      setSaving(null);
    }
  };

  const toggleShowInput = (envVar: string) => {
    setShowInputs((prev) => ({ ...prev, [envVar]: !prev[envVar] }));
  };

  const toggleEditMode = (envVar: string) => {
    setEditMode((prev) => ({ ...prev, [envVar]: !prev[envVar] }));
    // Clear validation when toggling
    setValidationResults((prev) => ({ ...prev, [envVar]: undefined as any }));
  };

  if (loading) {
    return (
      <div className="container py-12 text-center">
        <Loader2 className="h-8 w-8 animate-spin mx-auto" />
      </div>
    );
  }

  return (
    <div className="container py-8 max-w-3xl">
      {/* Back Link */}
      <Link
        href="/admin"
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to Studio
      </Link>

      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Settings</h1>
        <p className="text-muted-foreground">
          Configure API keys for transcription and AI services.
        </p>
      </div>

      {/* Info Card */}
      <Card className="mb-6 bg-blue-50 border-blue-200 dark:bg-blue-950 dark:border-blue-800">
        <CardContent className="pt-6">
          <div className="flex gap-3">
            <Info className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium mb-1">API Key Security</p>
              <p className="text-muted-foreground">
                Keys are stored securely in the backend environment. You can validate keys before saving.
                After saving, restart the backend for changes to fully take effect.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Required API Keys */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-4">Required Services</h2>
        <div className="space-y-4">
          {API_KEYS.filter((k) => k.required).map((keyConfig) => {
            const status = getKeyStatus(keyConfig.envVar);
            const isEditing = editMode[keyConfig.envVar];
            const validation = validationResults[keyConfig.envVar];
            const inputValue = keyInputs[keyConfig.envVar] || "";
            const showInput = showInputs[keyConfig.envVar];

            return (
              <Card key={keyConfig.envVar}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Key className="h-4 w-4 text-muted-foreground" />
                      <CardTitle className="text-lg">{keyConfig.name}</CardTitle>
                    </div>
                    {status?.configured ? (
                      <Badge variant="default" className="bg-green-500">
                        <Check className="h-3 w-3 mr-1" />
                        Configured
                      </Badge>
                    ) : (
                      <Badge variant="destructive">
                        <AlertTriangle className="h-3 w-3 mr-1" />
                        Required
                      </Badge>
                    )}
                  </div>
                  <CardDescription>{keyConfig.description}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {status?.configured && !isEditing ? (
                    <div className="flex items-center justify-between">
                      <code className="px-3 py-2 bg-muted rounded text-sm font-mono">
                        {status.masked_value}
                      </code>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => toggleEditMode(keyConfig.envVar)}
                        >
                          Update
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDelete(keyConfig.envVar)}
                          disabled={saving === keyConfig.envVar}
                          className="text-red-500 hover:text-red-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex gap-2">
                        <div className="relative flex-1">
                          <Input
                            type={showInput ? "text" : "password"}
                            placeholder={keyConfig.placeholder}
                            value={inputValue}
                            onChange={(e) =>
                              setKeyInputs((prev) => ({
                                ...prev,
                                [keyConfig.envVar]: e.target.value,
                              }))
                            }
                          />
                          <button
                            type="button"
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                            onClick={() => toggleShowInput(keyConfig.envVar)}
                          >
                            {showInput ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                        <Button
                          variant="outline"
                          onClick={() => handleValidate(keyConfig.envVar)}
                          disabled={!inputValue || validating === keyConfig.envVar}
                        >
                          {validating === keyConfig.envVar ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            "Test"
                          )}
                        </Button>
                        <Button
                          onClick={() => handleSave(keyConfig.envVar)}
                          disabled={!inputValue || saving === keyConfig.envVar}
                        >
                          {saving === keyConfig.envVar ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Save className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                      {validation && (
                        <div
                          className={`flex items-center gap-2 text-sm ${
                            validation.valid ? "text-green-600" : "text-red-600"
                          }`}
                        >
                          {validation.valid ? (
                            <CheckCircle className="h-4 w-4" />
                          ) : (
                            <XCircle className="h-4 w-4" />
                          )}
                          {validation.valid
                            ? "API key is valid!"
                            : validation.error || "Invalid API key"}
                        </div>
                      )}
                      {isEditing && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleEditMode(keyConfig.envVar)}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  )}
                  <a
                    href={keyConfig.docsUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center text-sm text-primary hover:underline"
                  >
                    Get API Key →
                  </a>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Transcription Providers */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-4">Transcription Providers</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Configure at least one transcription provider. Cloud providers are faster but require API keys.
          Local providers (Faster-Whisper) are free but slower.
        </p>
        <div className="space-y-4">
          {API_KEYS.filter((k) => !k.required).map((keyConfig) => {
            const status = getKeyStatus(keyConfig.envVar);
            const isEditing = editMode[keyConfig.envVar];
            const validation = validationResults[keyConfig.envVar];
            const inputValue = keyInputs[keyConfig.envVar] || "";
            const showInput = showInputs[keyConfig.envVar];

            return (
              <Card key={keyConfig.envVar}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Key className="h-4 w-4 text-muted-foreground" />
                      <CardTitle className="text-lg">{keyConfig.name}</CardTitle>
                    </div>
                    {status?.configured ? (
                      <Badge variant="default" className="bg-green-500">
                        <Check className="h-3 w-3 mr-1" />
                        Configured
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Optional</Badge>
                    )}
                  </div>
                  <CardDescription>{keyConfig.description}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {status?.configured && !isEditing ? (
                    <div className="flex items-center justify-between">
                      <code className="px-3 py-2 bg-muted rounded text-sm font-mono">
                        {status.masked_value}
                      </code>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => toggleEditMode(keyConfig.envVar)}
                        >
                          Update
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDelete(keyConfig.envVar)}
                          disabled={saving === keyConfig.envVar}
                          className="text-red-500 hover:text-red-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex gap-2">
                        <div className="relative flex-1">
                          <Input
                            type={showInput ? "text" : "password"}
                            placeholder={keyConfig.placeholder}
                            value={inputValue}
                            onChange={(e) =>
                              setKeyInputs((prev) => ({
                                ...prev,
                                [keyConfig.envVar]: e.target.value,
                              }))
                            }
                          />
                          <button
                            type="button"
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                            onClick={() => toggleShowInput(keyConfig.envVar)}
                          >
                            {showInput ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                        <Button
                          variant="outline"
                          onClick={() => handleValidate(keyConfig.envVar)}
                          disabled={!inputValue || validating === keyConfig.envVar}
                        >
                          {validating === keyConfig.envVar ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            "Test"
                          )}
                        </Button>
                        <Button
                          onClick={() => handleSave(keyConfig.envVar)}
                          disabled={!inputValue || saving === keyConfig.envVar}
                        >
                          {saving === keyConfig.envVar ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Save className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                      {validation && (
                        <div
                          className={`flex items-center gap-2 text-sm ${
                            validation.valid ? "text-green-600" : "text-red-600"
                          }`}
                        >
                          {validation.valid ? (
                            <CheckCircle className="h-4 w-4" />
                          ) : (
                            <XCircle className="h-4 w-4" />
                          )}
                          {validation.valid
                            ? "API key is valid!"
                            : validation.error || "Invalid API key"}
                        </div>
                      )}
                      {isEditing && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleEditMode(keyConfig.envVar)}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  )}
                  <a
                    href={keyConfig.docsUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center text-sm text-primary hover:underline"
                  >
                    Get API Key →
                  </a>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Local Providers */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-lg">Local Transcription (No API Key Required)</CardTitle>
          <CardDescription>
            These providers run locally on your machine using your GPU/CPU. Free but slower than cloud.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {providers
              .filter((p) => ["faster-whisper", "whisper"].includes(p.name))
              .map((provider) => (
                <div
                  key={provider.name}
                  className="flex items-center justify-between p-3 border rounded-lg"
                >
                  <div>
                    <p className="font-medium">{provider.display_name}</p>
                    <p className="text-sm text-muted-foreground">
                      {provider.note || "Free, uses local GPU/CPU"}
                    </p>
                  </div>
                  {provider.available ? (
                    <Badge variant="default" className="bg-green-500">
                      <Check className="h-3 w-3 mr-1" />
                      Available
                    </Badge>
                  ) : (
                    <Badge variant="secondary">Not Installed</Badge>
                  )}
                </div>
              ))}
            {providers.filter((p) => ["faster-whisper", "whisper"].includes(p.name)).length === 0 && (
              <p className="text-sm text-muted-foreground">
                No local providers detected. Install faster-whisper for free local transcription.
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
