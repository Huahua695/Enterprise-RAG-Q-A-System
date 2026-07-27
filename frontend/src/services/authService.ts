import api from './api'

export interface LoginData {
  username: string
  password: string
}

export interface RegisterData {
  username: string
  password: string
  email?: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export const authAPI = {
  login: (data: LoginData) =>
    api.post<TokenResponse>('/auth/login', data),

  register: (data: RegisterData) =>
    api.post('/auth/register', data),

  getMe: () =>
    api.get('/auth/me'),

  changePassword: (oldPassword: string, newPassword: string) =>
    api.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    }),
}
