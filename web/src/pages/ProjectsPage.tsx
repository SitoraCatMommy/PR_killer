import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { createProject, deleteProject, listProjects } from '../api/api';
import { ApiErrorText } from '../components/ApiErrorText';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Trash2 } from 'lucide-react';

const PAGE = 20;

export function ProjectsPage() {
  const [offset, setOffset] = useState(0);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const qc = useQueryClient();

  const list = useQuery({
    queryKey: qk.projects(offset, PAGE),
    queryFn: () => listProjects(offset, PAGE),
  });

  const create = useMutation({
    mutationFn: () => createProject({ name: name.trim(), description: description.trim() || null }),
    onSuccess: () => {
      setName('');
      setDescription('');
      void qc.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  const removeProject = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  const meta = list.data?.meta;
  const canPrev = offset > 0;
  const canNext = meta ? offset + meta.limit < meta.total : false;

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-semibold tracking-tight">{ru.projects.title}</h1>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>{ru.projects.newCard}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid max-w-xl gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) create.mutate();
            }}
          >
            <div className="space-y-2">
              <span className="text-sm font-medium">{ru.projects.name}</span>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={512}
                placeholder={ru.projects.namePh}
              />
            </div>
            <div className="space-y-2">
              <span className="text-sm font-medium">{ru.projects.description}</span>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder={ru.projects.descriptionPh}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={create.isPending || !name.trim()}>
                {create.isPending ? ru.projects.creating : ru.projects.create}
              </Button>
              {create.error && <ApiErrorText error={create.error} />}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>{ru.projects.listCard}</CardTitle>
          <CardDescription>
            {meta != null && (
              <>
                {ru.common.totalCount(meta.total)} · {ru.common.showing(list.data?.items.length ?? 0)}
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {list.isPending && <Skeleton className="h-40 w-full" />}
          {list.error && <ApiErrorText error={list.error} />}
          {list.data && (
            <>
              {!list.data.items.length ? (
                <p className="text-sm text-muted-foreground">{ru.projects.emptyList}</p>
              ) : (
                <>
                  <ul className="divide-y rounded-lg border">
                    {list.data.items.map((p) => (
                      <li key={p.id} className="flex items-stretch">
                        <Link
                          to={`/projects/${p.id}`}
                          className={cn(
                            buttonVariants({ variant: 'ghost' }),
                            'h-auto min-w-0 flex-1 justify-start rounded-none px-4 py-3 text-left font-normal hover:bg-muted/60',
                          )}
                        >
                          <div>
                            <div className="font-medium text-foreground">{p.name}</div>
                            <div className="font-mono text-xs text-muted-foreground">{p.id}</div>
                          </div>
                        </Link>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-auto shrink-0 rounded-none text-destructive hover:bg-destructive/10 hover:text-destructive"
                          disabled={removeProject.isPending}
                          aria-label={ru.projects.deleteProjectAria}
                          title={ru.projects.deleteProject}
                          onClick={(e) => {
                            e.preventDefault();
                            if (window.confirm(ru.projects.deleteProjectConfirm)) {
                              removeProject.mutate(p.id);
                            }
                          }}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </li>
                    ))}
                  </ul>
                  {removeProject.error && <ApiErrorText error={removeProject.error} className="mt-2" />}
                  <div className="mt-4 flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!canPrev}
                      onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
                    >
                      {ru.common.prev}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!canNext}
                      onClick={() => setOffset((o) => o + PAGE)}
                    >
                      {ru.common.next}
                    </Button>
                  </div>
                </>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
