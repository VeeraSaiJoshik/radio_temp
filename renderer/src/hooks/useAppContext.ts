import { createContext, useContext } from 'react';
import type { AppState } from '../store/appState';
import type { AppActions } from './useAppState';

export interface AppContextValue {
  state: AppState;
  actions: AppActions;
}

export const AppContext = createContext<AppContextValue | null>(null);

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error('useAppContext must be used within AppContext.Provider');
  }
  return ctx;
}
