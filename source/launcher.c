#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>
#include <stdio.h>
#ifndef APP_ENTRY
#define APP_ENTRY L"main_sorter.pyc"
#endif

int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,LPWSTR cmd,int show) {
    wchar_t root[32768], python[32768], script[32768], command[32768], message[512];
    DWORD n=GetModuleFileNameW(NULL,root,32768);
    if(!n || n>=32000) return 1;
    wchar_t *slash=wcsrchr(root,L'\\'); if(!slash) return 1; *slash=0;
    if(wcslen(root)>15000) { MessageBoxW(NULL,L"Extract the program to a shorter folder path.",L"FNV Audio Converter",MB_ICONERROR); return 1; }
    swprintf(python,32768,L"%ls\\runtime\\pythonw.exe",root);
    swprintf(script,32768,L"%ls\\app\\%ls",root,APP_ENTRY);
    if(GetFileAttributesW(python)==INVALID_FILE_ATTRIBUTES || GetFileAttributesW(script)==INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL,L"Extract the entire ZIP first, then run this EXE. Keep the app and runtime folders beside it.",L"FNV Audio Converter - Missing files",MB_ICONERROR); return 1;
    }
    SetDllDirectoryW(L"");
    swprintf(command,32768,L"\"%ls\" -I -B \"%ls\"",python,script);
    STARTUPINFOW si={0}; si.cb=sizeof(si); PROCESS_INFORMATION pi={0};
    if(!CreateProcessW(python,command,NULL,NULL,FALSE,CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW,NULL,root,&si,&pi)) {
        swprintf(message,512,L"The program could not start (Windows error %lu). Extract the complete package to a writable local folder. Windows 10/11 64-bit is required.",GetLastError());
        MessageBoxW(NULL,message,L"FNV Audio Converter - Startup error",MB_ICONERROR); return 1;
    }
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess); return 0;
}
