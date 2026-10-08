import AppShell from './components/layout/AppShell'
import ErrorBoundary from './components/layout/ErrorBoundary'
import { RulesetProvider } from './context/RulesetContext'
import { TextProvider } from './context/TextContext'
import { UIProvider } from './context/UIContext'

/**
 * Providers: RulesetProvider > UIProvider > TextProvider (TextProvider reads both).
 * The page-level ErrorBoundary sits outside the providers so corrupt saved state still gets a
 * friendly "Reset app data" screen. Layout: components/layout/AppShell (Task 4.10).
 */
export default function App() {
  return (
    <ErrorBoundary>
      <RulesetProvider>
        <UIProvider>
          <TextProvider>
            <AppShell />
          </TextProvider>
        </UIProvider>
      </RulesetProvider>
    </ErrorBoundary>
  )
}
