import { useState, useMemo } from 'react';
import { Search, ChevronRight, Play, Copy, Check, Server } from 'lucide-react';
import { Badge } from './components/ui/badge';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Card } from './components/ui/card';
import { ScrollArea } from './components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Textarea } from './components/ui/textarea';
import { cn } from './lib/utils';
import { API_CATEGORIES, SERVER_URL } from './generated-api-data';
import './index.css';

// ============================================================================
// Types
// ============================================================================

interface ApiParam {
  name: string;
  type: string;
  required: boolean;
  description: string;
  example?: string;
}

interface ApiEndpoint {
  method: string;
  path: string;
  summary: string;
  description?: string;
  pathParams?: ApiParam[];
  queryParams?: ApiParam[];
  bodySchema?: string;
  bodyExample?: string;
  responseExample?: string;
  tags: string[];
}

interface ApiCategory {
  name: string;
  description: string;
  endpoints: ApiEndpoint[];
}

// ============================================================================
// Method Badge Colors
// ============================================================================

const METHOD_COLORS: Record<string, string> = {
  GET: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
  POST: 'bg-green-500/10 text-green-600 border-green-500/20',
  PUT: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
  PATCH: 'bg-orange-500/10 text-orange-600 border-orange-500/20',
  DELETE: 'bg-red-500/10 text-red-600 border-red-500/20',
};

// ============================================================================
// Components
// ============================================================================

function MethodBadge({ method }: { method: string }) {
  return (
    <Badge variant="outline" className={cn('font-mono text-xs px-2', METHOD_COLORS[method])}>
      {method}
    </Badge>
  );
}

function CodeBlock({ code, language = 'json' }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group">
      <pre className="bg-muted rounded-md p-3 text-xs overflow-x-auto">
        <code className={`language-${language}`}>{code}</code>
      </pre>
      <Button
        size="sm"
        variant="ghost"
        className="absolute top-1 right-1 h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={handleCopy}
      >
        {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
      </Button>
    </div>
  );
}

function ApiTester({ endpoint }: { endpoint: ApiEndpoint }) {
  const [pathValues, setPathValues] = useState<Record<string, string>>({});
  const [queryValues, setQueryValues] = useState<Record<string, string>>({});
  const [body, setBody] = useState(endpoint.bodyExample || '');
  const [response, setResponse] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildUrl = () => {
    let path = endpoint.path;
    for (const [key, value] of Object.entries(pathValues)) {
      path = path.replace(`{${key}}`, encodeURIComponent(value));
    }
    const queryParts: string[] = [];
    for (const [key, value] of Object.entries(queryValues)) {
      if (value) queryParts.push(`${key}=${encodeURIComponent(value)}`);
    }
    const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
    return `${SERVER_URL}${path}${queryString}`;
  };

  const handleExecute = async () => {
    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const url = buildUrl();
      const headers: Record<string, string> = {};
      const options: RequestInit = { method: endpoint.method, headers };

      if (['POST', 'PUT', 'PATCH'].includes(endpoint.method) && body) {
        headers['Content-Type'] = 'application/json';
        options.body = body;
      }

      const res = await fetch(url, options);
      const text = await res.text();

      try {
        const json = JSON.parse(text);
        setResponse(JSON.stringify(json, null, 2));
      } catch {
        setResponse(text);
      }

      if (!res.ok) {
        setError(`${res.status} ${res.statusText}`);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 border-t pt-4 mt-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Try It Out</h4>
        <Button size="sm" onClick={handleExecute} disabled={loading}>
          <Play className="h-3 w-3 mr-1" />
          {loading ? 'Running...' : 'Execute'}
        </Button>
      </div>

      {endpoint.pathParams && endpoint.pathParams.length > 0 && (
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">Path Parameters</label>
          {endpoint.pathParams.map((param: ApiParam) => (
            <div key={param.name} className="flex items-center gap-2">
              <span className="text-xs font-mono w-24 shrink-0">{param.name}</span>
              <Input
                className="h-8 text-xs font-mono"
                placeholder={param.example || param.name}
                value={pathValues[param.name] || ''}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPathValues({ ...pathValues, [param.name]: e.target.value })}
              />
            </div>
          ))}
        </div>
      )}

      {endpoint.queryParams && endpoint.queryParams.length > 0 && (
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">Query Parameters</label>
          {endpoint.queryParams.map((param: ApiParam) => (
            <div key={param.name} className="flex items-center gap-2">
              <span className="text-xs font-mono w-24 shrink-0">
                {param.name}
                {param.required && <span className="text-red-500">*</span>}
              </span>
              <Input
                className="h-8 text-xs font-mono"
                placeholder={param.example || param.name}
                value={queryValues[param.name] || ''}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setQueryValues({ ...queryValues, [param.name]: e.target.value })}
              />
            </div>
          ))}
        </div>
      )}

      {['POST', 'PUT', 'PATCH'].includes(endpoint.method) && (
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">Request Body</label>
          <Textarea
            className="font-mono text-xs min-h-[120px]"
            value={body}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setBody(e.target.value)}
            placeholder="Enter JSON body..."
          />
        </div>
      )}

      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">Request URL</label>
        <div className="bg-muted rounded-md p-2 text-xs font-mono break-all">
          {endpoint.method} {buildUrl()}
        </div>
      </div>

      {(response || error) && (
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">
            Response {error && <span className="text-red-500">({error})</span>}
          </label>
          <CodeBlock code={response || ''} />
        </div>
      )}
    </div>
  );
}

function EndpointCard({ endpoint }: { endpoint: ApiEndpoint }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className={cn('transition-all', expanded && 'ring-1 ring-primary')}>
      <button
        className="w-full p-4 flex items-center gap-3 text-left hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <MethodBadge method={endpoint.method} />
        <code className="text-sm font-mono flex-1 truncate">{endpoint.path}</code>
        <span className="text-sm text-muted-foreground hidden sm:block">{endpoint.summary}</span>
        <ChevronRight className={cn('h-4 w-4 transition-transform', expanded && 'rotate-90')} />
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4">
          {endpoint.description && (
            <p className="text-sm text-muted-foreground">{endpoint.description}</p>
          )}

          <Tabs defaultValue="params" className="w-full">
            <TabsList className="h-8">
              <TabsTrigger value="params" className="text-xs">Parameters</TabsTrigger>
              {endpoint.bodyExample && <TabsTrigger value="body" className="text-xs">Body</TabsTrigger>}
              {endpoint.responseExample && <TabsTrigger value="response" className="text-xs">Response</TabsTrigger>}
              <TabsTrigger value="try" className="text-xs">Try It</TabsTrigger>
            </TabsList>

            <TabsContent value="params" className="mt-3">
              {(!endpoint.pathParams?.length && !endpoint.queryParams?.length) ? (
                <p className="text-sm text-muted-foreground">No parameters required.</p>
              ) : (
                <div className="space-y-3">
                  {endpoint.pathParams && endpoint.pathParams.length > 0 && (
                    <div>
                      <h5 className="text-xs font-semibold mb-2">Path Parameters</h5>
                      <div className="space-y-2">
                        {endpoint.pathParams.map((param: ApiParam) => (
                          <div key={param.name} className="flex items-start gap-2 text-sm">
                            <code className="bg-muted px-1 py-0.5 rounded text-xs">{param.name}</code>
                            <span className="text-muted-foreground text-xs">{param.type}</span>
                            {param.required && <Badge variant="outline" className="text-[10px]">required</Badge>}
                            <span className="text-xs">{param.description}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {endpoint.queryParams && endpoint.queryParams.length > 0 && (
                    <div>
                      <h5 className="text-xs font-semibold mb-2">Query Parameters</h5>
                      <div className="space-y-2">
                        {endpoint.queryParams.map((param: ApiParam) => (
                          <div key={param.name} className="flex items-start gap-2 text-sm">
                            <code className="bg-muted px-1 py-0.5 rounded text-xs">{param.name}</code>
                            <span className="text-muted-foreground text-xs">{param.type}</span>
                            {param.required && <Badge variant="outline" className="text-[10px]">required</Badge>}
                            <span className="text-xs">{param.description}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </TabsContent>

            {endpoint.bodyExample && (
              <TabsContent value="body" className="mt-3">
                <CodeBlock code={endpoint.bodyExample} />
              </TabsContent>
            )}

            {endpoint.responseExample && (
              <TabsContent value="response" className="mt-3">
                <CodeBlock code={endpoint.responseExample} />
              </TabsContent>
            )}

            <TabsContent value="try" className="mt-3">
              <ApiTester endpoint={endpoint} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </Card>
  );
}

// ============================================================================
// Main Page
// ============================================================================

export function ApiDocsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  const categories = API_CATEGORIES as unknown as ApiCategory[];

  const filteredCategories = useMemo(() => {
    if (!searchQuery && !selectedCategory) return categories;

    return categories.map((cat) => ({
      ...cat,
      endpoints: cat.endpoints.filter((ep) => {
        const matchesSearch = !searchQuery ||
          ep.path.toLowerCase().includes(searchQuery.toLowerCase()) ||
          ep.summary.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesCategory = !selectedCategory || cat.name === selectedCategory;
        return matchesSearch && matchesCategory;
      }),
    })).filter((cat) => cat.endpoints.length > 0);
  }, [searchQuery, selectedCategory, categories]);

  const totalEndpoints = categories.reduce((sum, cat) => sum + cat.endpoints.length, 0);

  return (
    <div className="api-docs-root flex h-full">

      {/* ── Left Sidebar — only shown in standalone /docs/ page ── */}
      <div className="w-56 shrink-0 border-r flex flex-col standalone-only">
        <div className="p-4 border-b">
          <img src="/agentspan-logo.svg" alt="Agentspan" className="h-6 mb-2" />
          <h3 className="text-sm font-semibold">API Reference</h3>
          <p className="text-xs text-muted-foreground mt-1">{totalEndpoints} endpoints</p>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-2">
            <button
              className={cn(
                'w-full text-left px-3 py-2 rounded-md text-sm flex items-center gap-2',
                'hover:bg-muted transition-colors',
                !selectedCategory && 'bg-muted font-medium'
              )}
              onClick={() => setSelectedCategory(null)}
            >
              All Endpoints
            </button>

            <div className="mt-3">
              {categories.map((cat) => (
                <button
                  key={cat.name}
                  className={cn(
                    'w-full text-left px-3 py-2 rounded-md text-sm flex items-center gap-2',
                    'hover:bg-muted transition-colors',
                    selectedCategory === cat.name && 'bg-muted font-medium'
                  )}
                  onClick={() => setSelectedCategory(cat.name)}
                >
                  <Server className="h-4 w-4 shrink-0" />
                  <span className="truncate">{cat.name}</span>
                  <Badge variant="secondary" className="text-[10px] ml-auto">{cat.endpoints.length}</Badge>
                </button>
              ))}
            </div>
          </div>
        </ScrollArea>
      </div>

      {/* ── Main content column ── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ── Header: search + horizontal category chips (embedded mode only) ── */}
        <div className="border-b p-4 space-y-3 shrink-0">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search endpoints..."
              value={searchQuery}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Category chips — only visible in embedded mode (hidden in standalone) */}
          <div className="embedded-only flex items-center gap-2 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
            <button
              className={cn(
                'shrink-0 px-3 py-1 rounded-full text-xs font-medium border transition-colors whitespace-nowrap',
                !selectedCategory
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-background text-muted-foreground border-border hover:border-primary hover:text-foreground'
              )}
              onClick={() => setSelectedCategory(null)}
            >
              All <span className="opacity-60">{totalEndpoints}</span>
            </button>
            {categories.map((cat) => (
              <button
                key={cat.name}
                className={cn(
                  'shrink-0 px-3 py-1 rounded-full text-xs font-medium border transition-colors whitespace-nowrap',
                  selectedCategory === cat.name
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-background text-muted-foreground border-border hover:border-primary hover:text-foreground'
                )}
                onClick={() => setSelectedCategory(selectedCategory === cat.name ? null : cat.name)}
              >
                {cat.name} <span className="opacity-60">{cat.endpoints.length}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ── Endpoint cards ── */}
        <ScrollArea className="flex-1 p-4">
          <div className="max-w-4xl mx-auto space-y-8">
            {filteredCategories.map((category) => (
              <div key={category.name}>
                <div className="flex items-center gap-2 mb-3">
                  <Server className="h-4 w-4" />
                  <h2 className="text-lg font-semibold">{category.name}</h2>
                </div>
                <p className="text-sm text-muted-foreground mb-4">{category.description}</p>
                <div className="space-y-2">
                  {category.endpoints.map((endpoint) => (
                    <EndpointCard
                      key={`${endpoint.method}-${endpoint.path}`}
                      endpoint={endpoint}
                    />
                  ))}
                </div>
              </div>
            ))}

            {filteredCategories.length === 0 && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">No endpoints found matching "{searchQuery}"</p>
              </div>
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
