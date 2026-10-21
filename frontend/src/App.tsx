import { createBrowserRouter, RouterProvider } from "react-router-dom";
import ChatPage from "./pages/ChatPage";
import DraftsPage from "./pages/DraftsPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <ChatPage />,
  },
  {
    path: "/drafts",
    element: <DraftsPage />,
  },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
