import React, { useCallback, useEffect, useState } from 'react';

const AUTH_URL = process.env.REACT_APP_AUTH_URL || 'http://localhost:8000';
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

type Me = {
  sub?: string;
  username?: string;
  email?: string;
  roles?: string[];
};

const ReportPage: React.FC = () => {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<unknown>(null);
  const [showConsent, setShowConsent] = useState(false);
  const [consentDone, setConsentDone] = useState(false);

  const fetchMe = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${AUTH_URL}/auth/me`, {
        credentials: 'include',
      });
      if (response.status === 401) {
        setMe(null);
        return;
      }
      if (!response.ok) {
        throw new Error('Failed to load session');
      }
      const data = await response.json();
      setMe(data);
    } catch (err) {
      setMe(null);
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const wantConsent = params.get('consent') === '1';
    if (wantConsent) {
      window.history.replaceState({}, '', window.location.pathname);
    }

    (async () => {
      await fetchMe();
      if (!wantConsent) {
        return;
      }
      // Не спрашивать повторно, если согласие уже есть в БД
      try {
        const response = await fetch(`${AUTH_URL}/auth/profile`, {
          credentials: 'include',
        });
        if (response.ok) {
          const data = await response.json();
          if (data.consent_given) {
            setConsentDone(true);
            setShowConsent(false);
            return;
          }
        }
      } catch {
        // fall through to show consent
      }
      setShowConsent(true);
    })();
  }, [fetchMe]);

  const login = () => {
    window.location.href = `${AUTH_URL}/auth/login`;
  };

  const logout = async () => {
    try {
      const response = await fetch(`${AUTH_URL}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json();
      setMe(null);
      if (data.logout_url) {
        window.location.href = data.logout_url;
      }
    } catch {
      setMe(null);
    }
  };

  const downloadReport = async () => {
    try {
      setReportLoading(true);
      setError(null);
      const response = await fetch(`${API_URL}/reports`, {
        credentials: 'include',
      });
      if (response.status === 401) {
        setMe(null);
        setError('Session expired — please login again');
        return;
      }
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || 'Failed to download report');
      }
      const data = await response.json();
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setReportLoading(false);
    }
  };

  const submitConsent = async (accepted: boolean) => {
    try {
      setError(null);
      const response = await fetch(`${AUTH_URL}/auth/consent`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ consent: accepted }),
      });
      if (!response.ok) {
        throw new Error('Failed to save consent');
      }
      setShowConsent(false);
      setConsentDone(accepted);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Consent error');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
  }

  if (!me) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <h1 className="text-2xl font-bold mb-4">BionicPRO Reports</h1>
        <p className="mb-6 text-gray-600 text-center max-w-md">
          Вход через bionicpro-auth (PKCE). Токены IdP не передаются в браузер —
          только HttpOnly session cookie.
        </p>
        <button
          onClick={login}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md w-full max-w-lg">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-2xl font-bold">Usage Reports</h1>
            <p className="text-sm text-gray-500 mt-1">
              {me.username || me.email} ({(me.roles || []).join(', ') || 'no roles'})
            </p>
          </div>
          <button
            onClick={logout}
            className="px-3 py-1 text-sm border rounded hover:bg-gray-50"
          >
            Logout
          </button>
        </div>

        {showConsent && (
          <div className="mb-6 p-4 border border-amber-300 bg-amber-50 rounded">
            <h2 className="font-semibold mb-2">Разрешение на использование данных</h2>
            <p className="text-sm text-gray-700 mb-4">
              Вы вошли через Яндекс ID. Разрешить сервису протезов сохранить и
              использовать данные вашего профиля?
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => submitConsent(true)}
                className="px-3 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                Разрешить
              </button>
              <button
                onClick={() => submitConsent(false)}
                className="px-3 py-2 border rounded hover:bg-gray-50"
              >
                Отклонить
              </button>
            </div>
          </div>
        )}

        {consentDone && (
          <div className="mb-4 p-3 bg-green-50 text-green-800 rounded text-sm">
            Профиль сохранён в локальной БД после вашего согласия.
          </div>
        )}

        <button
          onClick={downloadReport}
          disabled={reportLoading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            reportLoading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {reportLoading ? 'Generating Report...' : 'Download Report'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>
        )}

        {report != null && (
          <pre className="mt-4 p-4 bg-gray-50 rounded text-xs overflow-auto">
            {JSON.stringify(report, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
