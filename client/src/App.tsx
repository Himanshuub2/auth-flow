import {GoogleOAuthProvider,GoogleLogin} from '@react-oauth/google'
import axios from 'axios';
import './App.css'
import { useEffect } from 'react';

function App() {

  const handleLogin =async (res:any)=>{
    const token = res.credential;
    try{
      const user = await axios.get(`${import.meta.env.VITE_API_URL}/auth/login`,{
        headers:{
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        withCredentials: true,
      });
      console.log(user);  
    }catch(error){
      console.log(error);
    }
    
  }

  useEffect(()=>{
    const validateUser = async () => {
      const response = await axios.get(`${import.meta.env.VITE_API_URL}/auth/me`,{
        withCredentials: true,
        headers: {
          'Content-Type': 'application/json',
        },
      });
      if(response.status === 200){
        console.log(response.data.user);
      }else if (response.status === 401){
        handleLogin();
      }else{
        console.log('Error validating user');
      }
    }
    validateUser();
  },[])

  const handleProtectedAPI = async () => {
    try{
      const response = await axios.get(`${import.meta.env.VITE_API_URL}/auth/protected`,{
        withCredentials: true,
        headers: {
          'Content-Type': 'application/json',
        },
      });
      console.log(response);
    }catch(error){
      console.log(error);
    }
  }

  return (
    <>
     <GoogleOAuthProvider clientId={import.meta.env.VITE_GOOGLE_CLIENT_ID as string}>
        <h1>Hello World</h1>
        <GoogleLogin onSuccess={handleLogin} onError={() => {console.log('Error occured')}} />
        <button onClick={handleProtectedAPI}>Protected API</button>
     </GoogleOAuthProvider>
    </>
  )
}

export default App
