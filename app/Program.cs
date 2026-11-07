using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.WinForms;

namespace WildsBuff
{
    public class Host : Form
    {
        const int Port = 8777;
        const string Url = "http://127.0.0.1:8777";
        const int BaseW = 660;
        const int BaseH = 450;

        WebView2 web;
        bool pinned = false;

        [DllImport("user32.dll")] static extern bool ReleaseCapture();
        [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, int msg, int w, int l);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr h, int attr, ref int val, int size);

        public Host()
        {
            Text = "野蛮人 · BUFF 编排台";
            try
            {
                string icoPath = Path.Combine(AppContext.BaseDirectory, "app.ico");
                if (File.Exists(icoPath)) Icon = new Icon(icoPath, 32, 32);
                else Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch { }

            AutoScaleMode = AutoScaleMode.None;
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(21, 76, 134);
            DoubleBuffered = true;
            try { int pref = 2; DwmSetWindowAttribute(Handle, 33, ref pref, 4); } catch { }

            web = new WebView2();
            web.Dock = DockStyle.Fill;
            Controls.Add(web);

            Resize += delegate
            {
                if (web != null) web.Bounds = new Rectangle(0, 0, ClientSize.Width, ClientSize.Height);
            };
            Load += async delegate { LayoutByDpi(); await Init(); };
        }

        void LayoutByDpi()
        {
            float k = DeviceDpi / 96f;
            ClientSize = new Size((int)(BaseW * k), (int)(BaseH * k));
        }

        static void Log(string s)
        {
            try
            {
                File.AppendAllText(Path.Combine(Path.GetTempPath(), "wilds_buff_wv2.log"),
                    DateTime.Now.ToString("HH:mm:ss ") + s + Environment.NewLine);
            }
            catch { }
        }

        async Task Init()
        {
            try
            {
                Log("init start dpi=" + DeviceDpi);
                string data = Path.Combine(Path.GetTempPath(), "wilds_buff_wv2");
                var env = await Microsoft.Web.WebView2.Core.CoreWebView2Environment.CreateAsync(null, data, null);
                await web.EnsureCoreWebView2Async(env);
                web.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
                web.CoreWebView2.Settings.IsStatusBarEnabled = false;
                web.CoreWebView2.Settings.AreDevToolsEnabled = false;
                web.CoreWebView2.WebMessageReceived += OnWebMessage;
                web.CoreWebView2.Navigate(Url);
                Log("navigate");
            }
            catch (Exception ex)
            {
                Log("EX " + ex);
                MessageBox.Show("WebView2 初始化失败：" + ex.Message);
                try { Process.Start(Url); } catch { }
            }
        }

        void OnWebMessage(object sender, Microsoft.Web.WebView2.Core.CoreWebView2WebMessageReceivedEventArgs e)
        {
            string cmd = e.TryGetWebMessageAsString();
            if (string.IsNullOrEmpty(cmd)) return;
            switch (cmd)
            {
                case "drag":
                    ReleaseCapture();
                    SendMessage(Handle, 0xA1, 0x2, 0);
                    break;
                case "min":
                    WindowState = FormWindowState.Minimized;
                    break;
                case "close":
                    Close();
                    break;
                case "pin":
                    pinned = !pinned;
                    TopMost = pinned;
                    break;
            }
        }

        static bool PortOpen()
        {
            try
            {
                using (var c = new TcpClient())
                {
                    var ar = c.BeginConnect("127.0.0.1", Port, null, null);
                    if (!ar.AsyncWaitHandle.WaitOne(300)) return false;
                    c.EndConnect(ar);
                    return true;
                }
            }
            catch { return false; }
        }

        static string FindRoot()
        {
            string dir = AppDomain.CurrentDomain.BaseDirectory;
            for (int i = 0; i < 6 && dir != null; i++)
            {
                if (File.Exists(Path.Combine(dir, "server.py"))) return dir;
                DirectoryInfo up = Directory.GetParent(dir.TrimEnd(Path.DirectorySeparatorChar));
                dir = up == null ? null : up.FullName + Path.DirectorySeparatorChar;
            }
            return null;
        }

        static string FindPython()
        {
            string[] cands = new string[]
            {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\Python\Python313\pythonw.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\Python\Python312\pythonw.exe"),
                @"C:\Python313\pythonw.exe",
                @"C:\Python312\pythonw.exe"
            };
            foreach (string p in cands) if (File.Exists(p)) return p;
            return "pythonw.exe";
        }

        [STAThread]
        public static void Main()
        {
            try { Application.SetHighDpiMode(HighDpiMode.PerMonitorV2); } catch { }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string root = FindRoot();
            if (root != null && !PortOpen())
            {
                var psi = new ProcessStartInfo(FindPython(), "\"" + Path.Combine(root, "server.py") + "\"");
                psi.WorkingDirectory = root;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                try { Process.Start(psi); } catch { }
                for (int i = 0; i < 40 && !PortOpen(); i++) Thread.Sleep(150);
            }
            Application.Run(new Host());
        }
    }
}
