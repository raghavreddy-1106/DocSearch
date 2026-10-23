import React, { createContext, useContext, useState, useEffect } from 'react';
import { useAuth } from './AuthContext';

export type AppState = 'empty' | 'processing' | 'ready' | 'active';

export interface Evidence {
  document: string;
  page: number;
  text: string;
  status: string;
  score?: number;
}

export interface SearchPageResult {
  document: string;
  page: number;
  match_count: number;
  snippets: string[];
}

export interface SearchResults {
  query: string;
  mode: string;
  total_pages: number;
  total_matches: number;
  results: SearchPageResult[];
  related_results?: SearchPageResult[];
}

export interface QueryResponse {
  answer: string;
  status: string;
  confidence: string;
  evidence: Evidence[];
  search_results?: SearchResults;
  diagnostics?: Record<string, any>;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  description: string;
  icon: string;
  group?: string;
}

interface AppContextType {
  appState: AppState;
  setAppState: (state: AppState) => void;
  documentCount: number;
  setDocumentCount: (count: number | ((prev: number) => number)) => void;
  activeDocuments: string[];
  setActiveDocuments: (docs: string[]) => void;
  
  // Persisted search state
  savedQuery: string;
  setSavedQuery: (query: string) => void;
  savedResponse: QueryResponse | null;
  setSavedResponse: (res: QueryResponse | null) => void;
  savedActiveTab: 'pdf-answer' | 'ai-answer' | 'pages';
  setSavedActiveTab: (tab: 'pdf-answer' | 'ai-answer' | 'pages') => void;

  // Global Model Selection
  selectedModel: string;
  setSelectedModel: (modelId: string) => Promise<void>;
  models: ModelInfo[];
  setModels: (models: ModelInfo[]) => void;
  isSwitchingModel: boolean;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const { user, getAuthHeaders } = useAuth();
  const [appState, setAppState] = useState<AppState>('empty');
  const [documentCount, setDocumentCount] = useState(0);
  const [activeDocuments, setActiveDocuments] = useState<string[]>([]);
  
  const [savedQuery, setSavedQuery] = useState('');
  const [savedResponse, setSavedResponse] = useState<QueryResponse | null>(null);
  const [savedActiveTab, setSavedActiveTab] = useState<'pdf-answer' | 'ai-answer' | 'pages'>('pdf-answer');

  const [selectedModel, setSelectedModelLocal] = useState('gemini-1.5-flash');
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [isSwitchingModel, setIsSwitchingModel] = useState(false);

  // Sync documents and active documents to current logged in user
  useEffect(() => {
    if (user) {
      fetch('http://localhost:8000/api/v1/documents/list', {
        headers: getAuthHeaders()
      })
        .then(res => res.json())
        .then(data => {
          const docs = data.documents || [];
          setDocumentCount(docs.length);
          setActiveDocuments(docs.map((d: any) => d.filename));
          setAppState(docs.length > 0 ? 'ready' : 'empty');
        })
        .catch(() => {
          setDocumentCount(0);
          setActiveDocuments([]);
          setAppState('empty');
        });
    } else {
      setDocumentCount(0);
      setActiveDocuments([]);
      setAppState('empty');
    }
  }, [user]);

  // Fetch models from backend on mount
  useEffect(() => {
    fetch('http://localhost:8000/api/v1/ai-answer/models')
      .then(res => res.json())
      .then(data => {
        if (data.models) setModels(data.models);
        if (data.current_model) setSelectedModelLocal(data.current_model);
      })
      .catch(err => console.warn('Could not load models list:', err));
  }, []);

  const setSelectedModel = async (modelId: string) => {
    setIsSwitchingModel(true);
    setSelectedModelLocal(modelId);
    try {
      await fetch('http://localhost:8000/api/v1/ai-answer/models/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId }),
      });
    } catch (e) {
      console.warn('Backend model switch notification error:', e);
    } finally {
      setIsSwitchingModel(false);
    }
  };

  return (
    <AppContext.Provider value={{ 
      appState, setAppState, 
      documentCount, setDocumentCount,
      activeDocuments, setActiveDocuments,
      savedQuery, setSavedQuery,
      savedResponse, setSavedResponse,
      savedActiveTab, setSavedActiveTab,
      selectedModel, setSelectedModel,
      models, setModels,
      isSwitchingModel
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}
