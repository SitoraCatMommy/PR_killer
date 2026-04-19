import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getHealth, getHealthReady } from '../api/api';
import { ApiErrorText } from '../components/ApiErrorText';
import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';
import { ArrowRight } from 'lucide-react';

export function HomePage() {
  const health = useQuery({ queryKey: qk.health, queryFn: getHealth });
  const ready = useQuery({ queryKey: qk.healthReady, queryFn: getHealthReady });

  return (
    <div className="space-y-10">
      <div className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">{ru.home.title}</h1>
        <p className="max-w-2xl text-muted-foreground">{ru.home.welcomeLine}</p>
        <p className="text-xs text-muted-foreground">
          {ru.common.apiAddress}:{' '}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.8rem]">
            {import.meta.env.VITE_API_BASE_URL}
          </code>
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Link
          to="/projects"
          className={cn(
            buttonVariants({ variant: 'outline' }),
            'flex h-auto items-center justify-between gap-2 py-4',
          )}
        >
          <span className="font-medium">{ru.home.ctaProjects}</span>
          <ArrowRight className="size-4 shrink-0 opacity-60" />
        </Link>
        <Link
          to="/materials"
          className={cn(
            buttonVariants({ variant: 'outline' }),
            'flex h-auto items-center justify-between gap-2 py-4',
          )}
        >
          <span className="font-medium">{ru.home.ctaMaterials}</span>
          <ArrowRight className="size-4 shrink-0 opacity-60" />
        </Link>
        <Link
          to="/analytics"
          className={cn(
            buttonVariants({ variant: 'outline' }),
            'flex h-auto items-center justify-between gap-2 py-4',
          )}
        >
          <span className="font-medium">{ru.home.ctaAnalytics}</span>
          <ArrowRight className="size-4 shrink-0 opacity-60" />
        </Link>
      </div>

      <Card className="max-w-lg shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg">{ru.home.apiCard}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {health.isPending && <Skeleton className="h-20 w-full" />}
          {health.error && <ApiErrorText error={health.error} />}
          {health.data && (
            <ul className="space-y-2 text-sm">
              <li className="flex justify-between gap-4">
                <span className="text-muted-foreground">{ru.home.status}</span>
                <Badge variant="secondary">{health.data.status}</Badge>
              </li>
              <li className="flex justify-between gap-4">
                <span className="text-muted-foreground">{ru.home.app}</span>
                <span className="font-medium">{health.data.app}</span>
              </li>
              <li className="flex justify-between gap-4">
                <span className="text-muted-foreground">{ru.home.environment}</span>
                <span className="font-medium">{health.data.environment}</span>
              </li>
            </ul>
          )}
          {ready.data && (
            <CardDescription>
              {ru.home.readiness}: {ready.data.status}
              {ready.data.redis !== undefined
                ? ` · ${ready.data.redis ? ru.home.redisOk : ru.home.redisDown}`
                : null}
            </CardDescription>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
