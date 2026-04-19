import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import { RootLayout } from './layouts/RootLayout';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { HomePage } from './pages/HomePage';
import { MaterialDetailPage } from './pages/MaterialDetailPage';
import { MaterialsPage } from './pages/MaterialsPage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { SourceAudioPage } from './pages/SourceAudioPage';
import { SourceDocumentPage } from './pages/SourceDocumentPage';

const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'projects/:projectId', element: <ProjectDetailPage /> },
      { path: 'sources/documents/:documentId', element: <SourceDocumentPage /> },
      { path: 'sources/audios/:audioId', element: <SourceAudioPage /> },
      { path: 'materials', element: <MaterialsPage /> },
      { path: 'materials/:materialId', element: <MaterialDetailPage /> },
      { path: 'analytics', element: <AnalyticsPage /> },
      { path: 'insights', element: <Navigate to="/analytics" replace /> },
      { path: 'dashboard', element: <Navigate to="/analytics" replace /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
